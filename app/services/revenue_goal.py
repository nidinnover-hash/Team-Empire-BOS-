"""Revenue goal tracking service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revenue_goal import RevenueGoal


async def create_goal(db: AsyncSession, *, organization_id: int, **kw) -> RevenueGoal:
    row = RevenueGoal(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_goal(db: AsyncSession, goal_id: int, org_id: int) -> RevenueGoal | None:
    return (await db.execute(select(RevenueGoal).where(RevenueGoal.id == goal_id, RevenueGoal.organization_id == org_id))).scalar_one_or_none()


async def list_goals(db: AsyncSession, org_id: int, *, scope: str | None = None, period: str | None = None) -> list[RevenueGoal]:
    q = select(RevenueGoal).where(RevenueGoal.organization_id == org_id)
    if scope:
        q = q.where(RevenueGoal.scope == scope)
    if period:
        q = q.where(RevenueGoal.period == period)
    q = q.order_by(RevenueGoal.period.desc())
    return list((await db.execute(q)).scalars().all())


async def update_progress(db: AsyncSession, goal_id: int, org_id: int, current_amount: float) -> RevenueGoal | None:
    row = await get_goal(db, goal_id, org_id)
    if not row:
        return None
    row.current_amount = current_amount
    row.gap = max(row.target_amount - current_amount, 0)
    row.attainment_pct = round(current_amount / max(row.target_amount, 1) * 100, 1)
    row.status = "achieved" if current_amount >= row.target_amount else "active"
    await db.commit()
    await db.refresh(row)
    return row


async def get_gap_analysis(db: AsyncSession, org_id: int, period: str) -> dict:
    goals = await list_goals(db, org_id, period=period)
    total_target = sum(g.target_amount for g in goals)
    total_current = sum(g.current_amount for g in goals)
    achieved = sum(1 for g in goals if g.status == "achieved")
    return {
        "period": period,
        "goal_count": len(goals),
        "achieved": achieved,
        "total_target": round(total_target, 2),
        "total_current": round(total_current, 2),
        "total_gap": round(max(total_target - total_current, 0), 2),
        "overall_attainment": round(total_current / max(total_target, 1) * 100, 1),
    }
