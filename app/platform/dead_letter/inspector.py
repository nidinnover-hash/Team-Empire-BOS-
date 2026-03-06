"""Dead-letter inspector — query and filter dead-letter entries."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dead_letter import DeadLetterEntry


async def list_entries(
    db: AsyncSession,
    organization_id: int,
    *,
    status: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[DeadLetterEntry]:
    """List dead-letter entries for an org, optionally filtered by status/source_type."""
    q = select(DeadLetterEntry).where(
        DeadLetterEntry.organization_id == organization_id,
    )
    if status:
        q = q.where(DeadLetterEntry.status == status)
    if source_type:
        q = q.where(DeadLetterEntry.source_type == source_type)
    q = q.order_by(DeadLetterEntry.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_entry(
    db: AsyncSession,
    entry_id: int,
    organization_id: int,
) -> DeadLetterEntry | None:
    """Get a single dead-letter entry by ID."""
    result = await db.execute(
        select(DeadLetterEntry).where(
            DeadLetterEntry.id == entry_id,
            DeadLetterEntry.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def count_by_status(
    db: AsyncSession,
    organization_id: int,
) -> dict[str, int]:
    """Return counts of dead-letter entries grouped by status."""
    result = await db.execute(
        select(
            DeadLetterEntry.status,
            func.count(DeadLetterEntry.id),
        )
        .where(DeadLetterEntry.organization_id == organization_id)
        .group_by(DeadLetterEntry.status)
    )
    return {status: count for status, count in result.all()}


async def count_by_source_type(
    db: AsyncSession,
    organization_id: int,
) -> dict[str, int]:
    """Return counts of dead-letter entries grouped by source_type."""
    result = await db.execute(
        select(
            DeadLetterEntry.source_type,
            func.count(DeadLetterEntry.id),
        )
        .where(DeadLetterEntry.organization_id == organization_id)
        .group_by(DeadLetterEntry.source_type)
    )
    return {source_type: count for source_type, count in result.all()}
