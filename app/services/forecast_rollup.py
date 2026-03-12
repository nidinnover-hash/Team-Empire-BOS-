"""Sales forecast rollup service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast_rollup import ForecastRollup
from app.services._guardrails import apply_safe_updates, get_tenant_row, tenant_select

_PROTECTED_FIELDS = {"id", "organization_id", "created_at"}


async def upsert_rollup(db: AsyncSession, *, organization_id: int, **kw) -> ForecastRollup:
    # Natural key: (organization_id, period, group_by, group_value)
    period = kw.get("period")
    group_by = kw.get("group_by")
    group_value = kw.get("group_value")
    if period and group_by and group_value:
        existing = (await db.execute(
            select(ForecastRollup).where(
                ForecastRollup.organization_id == organization_id,
                ForecastRollup.period == period,
                ForecastRollup.group_by == group_by,
                ForecastRollup.group_value == group_value,
            )
        )).scalar_one_or_none()
        if existing:
            apply_safe_updates(existing, kw, protected_fields=_PROTECTED_FIELDS)
            await db.commit()
            await db.refresh(existing)
            return existing
    row = ForecastRollup(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_rollup(db: AsyncSession, rollup_id: int, org_id: int) -> ForecastRollup | None:
    return await get_tenant_row(db, ForecastRollup, rollup_id, org_id)


async def list_rollups(db: AsyncSession, org_id: int, *, period: str | None = None, group_by: str | None = None) -> list[ForecastRollup]:
    q = tenant_select(ForecastRollup, org_id)
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
