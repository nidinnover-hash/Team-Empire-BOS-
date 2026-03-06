"""Signal query helpers for operational and intelligence paths."""

from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal


def _base_query() -> Select[tuple[Signal]]:
    return select(Signal).order_by(desc(Signal.occurred_at), desc(Signal.id))


async def list_signals_by_entity(
    db: AsyncSession,
    *,
    organization_id: int,
    entity_type: str,
    entity_id: str,
    limit: int = 100,
) -> list[Signal]:
    result = await db.execute(
        _base_query()
        .where(
            Signal.organization_id == organization_id,
            Signal.entity_type == entity_type,
            Signal.entity_id == entity_id,
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_signals_by_correlation(
    db: AsyncSession,
    *,
    organization_id: int,
    correlation_id: str,
    limit: int = 100,
) -> list[Signal]:
    result = await db.execute(
        _base_query()
        .where(
            Signal.organization_id == organization_id,
            Signal.correlation_id == correlation_id,
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_recent_signals_by_org(
    db: AsyncSession,
    *,
    organization_id: int,
    limit: int = 100,
) -> list[Signal]:
    result = await db.execute(
        _base_query()
        .where(Signal.organization_id == organization_id)
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_recent_signals_by_topic(
    db: AsyncSession,
    *,
    organization_id: int,
    topic: str,
    limit: int = 100,
) -> list[Signal]:
    result = await db.execute(
        _base_query()
        .where(
            Signal.organization_id == organization_id,
            Signal.topic == topic,
        )
        .limit(limit)
    )
    return list(result.scalars().all())
