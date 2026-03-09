"""Deal velocity service — stage transition tracking and bottleneck analysis."""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal_velocity import DealStageTransition

DEAL_STAGES = ["discovery", "proposal", "negotiation", "contract", "won", "lost"]


async def record_transition(
    db: AsyncSession, organization_id: int, deal_id: int,
    from_stage: str | None, to_stage: str,
    hours_in_stage: float | None = None, changed_by: int | None = None,
) -> DealStageTransition:
    t = DealStageTransition(
        organization_id=organization_id, deal_id=deal_id,
        from_stage=from_stage, to_stage=to_stage,
        hours_in_stage=hours_in_stage, changed_by_user_id=changed_by,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def get_deal_history(
    db: AsyncSession, organization_id: int, deal_id: int,
) -> list[DealStageTransition]:
    result = await db.execute(
        select(DealStageTransition).where(
            DealStageTransition.organization_id == organization_id,
            DealStageTransition.deal_id == deal_id,
        ).order_by(DealStageTransition.created_at)
    )
    return list(result.scalars().all())


async def get_stage_velocity(
    db: AsyncSession, organization_id: int,
) -> dict:
    """Calculate average hours spent in each stage."""
    result = await db.execute(
        select(
            DealStageTransition.from_stage,
            func.avg(DealStageTransition.hours_in_stage).label("avg_hours"),
            func.count().label("transitions"),
        )
        .where(
            DealStageTransition.organization_id == organization_id,
            DealStageTransition.from_stage.isnot(None),
            DealStageTransition.hours_in_stage.isnot(None),
        )
        .group_by(DealStageTransition.from_stage)
    )
    stages = {}
    for row in result.all():
        stages[row.from_stage] = {
            "avg_hours": round(float(row.avg_hours), 1) if row.avg_hours else 0,
            "transitions": row.transitions,
        }
    return {"stages": DEAL_STAGES, "velocity": stages}


async def get_bottlenecks(
    db: AsyncSession, organization_id: int, threshold_hours: float = 48,
) -> list[dict]:
    """Find stages where average time exceeds threshold."""
    velocity = await get_stage_velocity(db, organization_id)
    bottlenecks = []
    for stage, data in velocity["velocity"].items():
        if data["avg_hours"] > threshold_hours:
            bottlenecks.append({
                "stage": stage, "avg_hours": data["avg_hours"],
                "transitions": data["transitions"],
                "exceeds_by_hours": round(data["avg_hours"] - threshold_hours, 1),
            })
    return sorted(bottlenecks, key=lambda x: x["avg_hours"], reverse=True)
