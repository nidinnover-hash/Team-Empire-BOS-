"""Pipeline conversion funnel service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversion_funnel import ConversionFunnel


async def upsert_stage(db: AsyncSession, *, organization_id: int, **kw) -> ConversionFunnel:
    row = ConversionFunnel(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_funnel(db: AsyncSession, org_id: int, *, period: str | None = None) -> list[ConversionFunnel]:
    q = select(ConversionFunnel).where(ConversionFunnel.organization_id == org_id)
    if period:
        q = q.where(ConversionFunnel.period == period)
    q = q.order_by(ConversionFunnel.from_stage, ConversionFunnel.to_stage)
    return list((await db.execute(q)).scalars().all())


async def get_funnel_summary(db: AsyncSession, org_id: int, period: str) -> dict:
    stages = await list_funnel(db, org_id, period=period)
    if not stages:
        return {"period": period, "stages": [], "overall_conversion": 0}
    stage_list = []
    for s in stages:
        stage_list.append({
            "from_stage": s.from_stage,
            "to_stage": s.to_stage,
            "entered": s.entered_count,
            "converted": s.converted_count,
            "rate": s.conversion_rate,
            "avg_time_hours": s.avg_time_hours,
        })
    first_entered = stages[0].entered_count if stages else 1
    last_converted = stages[-1].converted_count if stages else 0
    overall = round(last_converted / max(first_entered, 1) * 100, 1)
    return {"period": period, "stages": stage_list, "overall_conversion": overall}


async def get_bottlenecks(db: AsyncSession, org_id: int, period: str) -> list[dict]:
    stages = await list_funnel(db, org_id, period=period)
    bottlenecks = []
    for s in stages:
        if s.conversion_rate < 50.0:
            bottlenecks.append({
                "from_stage": s.from_stage,
                "to_stage": s.to_stage,
                "conversion_rate": s.conversion_rate,
                "avg_time_hours": s.avg_time_hours,
                "drop_off": s.entered_count - s.converted_count,
            })
    return sorted(bottlenecks, key=lambda x: x["conversion_rate"])
