"""Team quota service — CRUD and progress tracking."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team_quota import TeamQuota


async def create_quota(db: AsyncSession, organization_id: int, **kwargs) -> TeamQuota:
    quota = TeamQuota(organization_id=organization_id, **kwargs)
    db.add(quota)
    await db.commit()
    await db.refresh(quota)
    return quota


async def list_quotas(
    db: AsyncSession, organization_id: int,
    user_id: int | None = None, period: str | None = None, active_only: bool = True,
) -> list[TeamQuota]:
    q = select(TeamQuota).where(TeamQuota.organization_id == organization_id)
    if user_id:
        q = q.where(TeamQuota.user_id == user_id)
    if period:
        q = q.where(TeamQuota.period == period)
    if active_only:
        q = q.where(TeamQuota.is_active.is_(True))
    result = await db.execute(q.order_by(TeamQuota.period_start.desc()))
    return list(result.scalars().all())


async def update_quota(
    db: AsyncSession, quota_id: int, organization_id: int, **kwargs,
) -> TeamQuota | None:
    result = await db.execute(
        select(TeamQuota).where(
            TeamQuota.id == quota_id, TeamQuota.organization_id == organization_id,
        )
    )
    quota = result.scalar_one_or_none()
    if not quota:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(quota, k):
            setattr(quota, k, v)
    await db.commit()
    await db.refresh(quota)
    return quota


async def update_progress(
    db: AsyncSession, quota_id: int, organization_id: int, value: float,
) -> TeamQuota | None:
    result = await db.execute(
        select(TeamQuota).where(
            TeamQuota.id == quota_id, TeamQuota.organization_id == organization_id,
        )
    )
    quota = result.scalar_one_or_none()
    if not quota:
        return None
    quota.current_value = value
    await db.commit()
    await db.refresh(quota)
    return quota


async def delete_quota(db: AsyncSession, quota_id: int, organization_id: int) -> bool:
    result = await db.execute(
        select(TeamQuota).where(
            TeamQuota.id == quota_id, TeamQuota.organization_id == organization_id,
        )
    )
    quota = result.scalar_one_or_none()
    if not quota:
        return False
    quota.is_active = False
    await db.commit()
    return True


async def get_team_progress(
    db: AsyncSession, organization_id: int, period: str | None = None,
) -> list[dict]:
    """Get quota progress for all team members."""
    quotas = await list_quotas(db, organization_id, period=period)
    return [
        {
            "id": q.id, "user_id": q.user_id, "quota_type": q.quota_type,
            "period": q.period, "target_value": q.target_value,
            "current_value": q.current_value,
            "progress_pct": round((q.current_value / q.target_value * 100), 1) if q.target_value else 0,
        }
        for q in quotas
    ]
