"""Sales forecast rollup service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast_rollup import ForecastRollup


async def upsert_rollup(db: AsyncSession, *, organization_id: int, **kw) -> ForecastRollup:
    row = ForecastRollup(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_rollup(db: AsyncSession, rollup_id: int, org_id: int) -> ForecastRollup | None:
    return (await db.execute(select(ForecastRollup).where(ForecastRollup.id == rollup_id, ForecastRollup.organization_id == org_id))).scalar_one_or_none()


async def list_rollups(db: AsyncSession, org_id: int, *, period: str | None = None, group_by: str | None = None) -> list[ForecastRollup]:
    q = select(ForecastRollup).where(ForecastRollup.organization_id == org_id)
    if period:
        q = q.where(ForecastRollup.period == period)
    if group_by:
        q = q.where(ForecastRollup.group_by == group_by)
    q = q.order_by(ForecastRollup.attainment_pct.desc())
    return list((await db.execute(q)).scalars().all())


async def get_period_summary(db: AsyncSession, org_id: int, period: str) -> dict:
    rollups = await list_rollups(db, org_id, period=period)
    if not rollups:
        return {"period": period, "total_committed": 0, "total_best_case": 0, "total_pipeline": 0, "total_closed_won": 0, "total_target": 0, "overall_attainment": 0}
    return {
        "period": period,
        "total_committed": round(sum(r.committed for r in rollups), 2),
        "total_best_case": round(sum(r.best_case for r in rollups), 2),
        "total_pipeline": round(sum(r.pipeline for r in rollups), 2),
        "total_closed_won": round(sum(r.closed_won for r in rollups), 2),
        "total_target": round(sum(r.target for r in rollups), 2),
        "overall_attainment": round(sum(r.closed_won for r in rollups) / max(sum(r.target for r in rollups), 1) * 100, 1),
    }
