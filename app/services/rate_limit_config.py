"""API rate limiting config service — CRUD and usage tracking."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rate_limit_config import RateLimitConfig


async def create_config(db: AsyncSession, organization_id: int, **kwargs) -> RateLimitConfig:
    config = RateLimitConfig(organization_id=organization_id, **kwargs)
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def list_configs(
    db: AsyncSession, organization_id: int, active_only: bool = True,
) -> list[RateLimitConfig]:
    q = select(RateLimitConfig).where(RateLimitConfig.organization_id == organization_id)
    if active_only:
        q = q.where(RateLimitConfig.is_active.is_(True))
    result = await db.execute(q.order_by(RateLimitConfig.id))
    return list(result.scalars().all())


async def update_config(
    db: AsyncSession, config_id: int, organization_id: int, **kwargs,
) -> RateLimitConfig | None:
    result = await db.execute(
        select(RateLimitConfig).where(
            RateLimitConfig.id == config_id,
            RateLimitConfig.organization_id == organization_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(config, k):
            setattr(config, k, v)
    await db.commit()
    await db.refresh(config)
    return config


async def delete_config(db: AsyncSession, config_id: int, organization_id: int) -> bool:
    result = await db.execute(
        select(RateLimitConfig).where(
            RateLimitConfig.id == config_id,
            RateLimitConfig.organization_id == organization_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return False
    config.is_active = False
    await db.commit()
    return True


async def record_request(
    db: AsyncSession, config_id: int, throttled: bool = False,
) -> None:
    result = await db.execute(select(RateLimitConfig).where(RateLimitConfig.id == config_id))
    config = result.scalar_one_or_none()
    if config:
        config.total_requests_tracked += 1
        if throttled:
            config.total_throttled += 1
        await db.commit()


async def get_usage_summary(db: AsyncSession, organization_id: int) -> list[dict]:
    configs = await list_configs(db, organization_id, active_only=False)
    return [
        {
            "id": c.id, "name": c.name, "endpoint_pattern": c.endpoint_pattern,
            "requests_per_minute": c.requests_per_minute,
            "total_requests": c.total_requests_tracked,
            "total_throttled": c.total_throttled,
            "throttle_rate_pct": round(c.total_throttled / c.total_requests_tracked * 100, 1) if c.total_requests_tracked else 0,
        }
        for c in configs
    ]
