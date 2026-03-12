"""Webhook event log service."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_event import WebhookEvent


async def capture_event(
    db: AsyncSession, *, organization_id: int, source: str,
    event_type: str, payload: dict | None = None,
    headers: dict | None = None,
) -> WebhookEvent:
    row = WebhookEvent(
        organization_id=organization_id, source=source,
        event_type=event_type,
        payload_json=json.dumps(payload or {}),
        headers_json=json.dumps(headers or {}),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_events(
    db: AsyncSession, organization_id: int, *,
    source: str | None = None, status: str | None = None,
    limit: int = 100,
) -> list[WebhookEvent]:
    q = select(WebhookEvent).where(WebhookEvent.organization_id == organization_id)
    if source:
        q = q.where(WebhookEvent.source == source)
    if status:
        q = q.where(WebhookEvent.status == status)
    q = q.order_by(WebhookEvent.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_event(db: AsyncSession, event_id: int, organization_id: int) -> WebhookEvent | None:
    q = select(WebhookEvent).where(WebhookEvent.id == event_id, WebhookEvent.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def mark_processed(db: AsyncSession, event_id: int, organization_id: int, error: str | None = None) -> WebhookEvent | None:
    row = await get_event(db, event_id, organization_id)
    if not row:
        return None
    row.status = "failed" if error else "processed"
    row.error_message = error
    row.processed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return row


async def replay_event(db: AsyncSession, event_id: int, organization_id: int) -> WebhookEvent | None:
    original = await get_event(db, event_id, organization_id)
    if not original:
        return None
    clone = WebhookEvent(
        organization_id=organization_id, source=original.source,
        event_type=original.event_type,
        payload_json=original.payload_json,
        headers_json=original.headers_json,
        status="replayed",
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return clone


async def get_stats(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(WebhookEvent.status, func.count(WebhookEvent.id))
        .where(WebhookEvent.organization_id == organization_id)
        .group_by(WebhookEvent.status)
    )).all()
    return {status: count for status, count in rows}
