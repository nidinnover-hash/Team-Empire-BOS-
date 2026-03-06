"""Dead-letter reprocessor — retry and archive dead-letter entries."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dead_letter import DeadLetterEntry

logger = logging.getLogger(__name__)


async def retry_entry(
    db: AsyncSession,
    entry_id: int,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
) -> DeadLetterEntry | None:
    """Mark a dead-letter entry for retry.

    Increments attempts, sets status to 'retrying', and clears resolved_at.
    The actual re-execution is handled by the caller based on source_type.
    Returns the updated entry, or None if not found.
    """
    result = await db.execute(
        select(DeadLetterEntry).where(
            DeadLetterEntry.id == entry_id,
            DeadLetterEntry.organization_id == organization_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    if entry.status in ("resolved", "archived"):
        return entry  # already terminal

    entry.status = "retrying"
    entry.attempts += 1
    entry.resolved_at = None
    await db.commit()
    await db.refresh(entry)
    return entry


async def resolve_entry(
    db: AsyncSession,
    entry_id: int,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
) -> DeadLetterEntry | None:
    """Mark a dead-letter entry as resolved (retry succeeded)."""
    result = await db.execute(
        select(DeadLetterEntry).where(
            DeadLetterEntry.id == entry_id,
            DeadLetterEntry.organization_id == organization_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    entry.status = "resolved"
    entry.resolved_at = datetime.now(UTC)
    entry.resolved_by = actor_user_id
    await db.commit()
    await db.refresh(entry)
    return entry


async def archive_entry(
    db: AsyncSession,
    entry_id: int,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
) -> DeadLetterEntry | None:
    """Archive a dead-letter entry (dismiss without retry)."""
    result = await db.execute(
        select(DeadLetterEntry).where(
            DeadLetterEntry.id == entry_id,
            DeadLetterEntry.organization_id == organization_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    entry.status = "archived"
    entry.resolved_at = datetime.now(UTC)
    entry.resolved_by = actor_user_id
    await db.commit()
    await db.refresh(entry)
    return entry


async def archive_old_entries(
    db: AsyncSession,
    organization_id: int,
    *,
    days: int = 30,
) -> int:
    """Archive dead-letter entries older than `days` that are still pending."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        update(DeadLetterEntry)
        .where(
            DeadLetterEntry.organization_id == organization_id,
            DeadLetterEntry.status == "pending",
            DeadLetterEntry.created_at < cutoff,
        )
        .values(status="archived", resolved_at=datetime.now(UTC))
    )
    await db.commit()
    return result.rowcount  # type: ignore[return-value]
