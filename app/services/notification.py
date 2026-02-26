"""Notification service — create, list, and manage notifications."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    *,
    organization_id: int,
    type: str,
    severity: str,
    title: str,
    message: str,
    user_id: int | None = None,
    source: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> Notification:
    """Create a new notification. Caller must commit."""
    entry = Notification(
        organization_id=organization_id,
        user_id=user_id,
        type=type,
        severity=severity,
        title=title,
        message=message,
        source=source,
        entity_type=entity_type,
        entity_id=entity_id,
        created_at=datetime.now(UTC),
    )
    db.add(entry)
    return entry


async def list_notifications(
    db: AsyncSession,
    organization_id: int,
    user_id: int | None = None,
    *,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    query = (
        select(Notification)
        .where(Notification.organization_id == organization_id)
    )
    if user_id is not None:
        query = query.where(
            (Notification.user_id == user_id) | (Notification.user_id.is_(None))
        )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    query = query.order_by(Notification.created_at.desc()).limit(max(1, min(limit, 200)))
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_unread_count(
    db: AsyncSession,
    organization_id: int,
    user_id: int | None = None,
) -> int:
    query = (
        select(func.count(Notification.id))
        .where(
            Notification.organization_id == organization_id,
            Notification.is_read.is_(False),
        )
    )
    if user_id is not None:
        query = query.where(
            (Notification.user_id == user_id) | (Notification.user_id.is_(None))
        )
    result = await db.execute(query)
    return int(result.scalar_one() or 0)


async def mark_read(
    db: AsyncSession,
    organization_id: int,
    notification_ids: list[int],
) -> int:
    """Mark specific notifications as read. Returns number updated."""
    if not notification_ids:
        return 0
    safe_ids = notification_ids[:100]
    result = await db.execute(
        update(Notification)
        .where(
            Notification.organization_id == organization_id,
            Notification.id.in_(safe_ids),
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    return int(result.rowcount or 0)


async def mark_all_read(
    db: AsyncSession,
    organization_id: int,
    user_id: int | None = None,
) -> int:
    """Mark all unread notifications as read for an org/user. Returns count."""
    query = (
        update(Notification)
        .where(
            Notification.organization_id == organization_id,
            Notification.is_read.is_(False),
        )
    )
    if user_id is not None:
        query = query.where(
            (Notification.user_id == user_id) | (Notification.user_id.is_(None))
        )
    result = await db.execute(query.values(is_read=True))
    return int(result.rowcount or 0)
