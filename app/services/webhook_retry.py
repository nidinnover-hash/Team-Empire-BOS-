"""Webhook retry queue service — exponential backoff for failed deliveries."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_retry import WebhookRetry

BACKOFF_BASE_MINUTES = 5  # 5, 25, 125, 625, 3125 min


def _next_retry_delay(attempt: int) -> timedelta:
    """Exponential backoff: base * 5^attempt minutes."""
    return timedelta(minutes=BACKOFF_BASE_MINUTES * (5 ** attempt))


async def enqueue_retry(
    db: AsyncSession, organization_id: int, webhook_id: int,
    event_type: str, payload: dict, delivery_id: int | None = None,
    max_attempts: int = 5,
) -> WebhookRetry:
    retry = WebhookRetry(
        organization_id=organization_id, webhook_id=webhook_id,
        event_type=event_type, payload_json=json.dumps(payload),
        delivery_id=delivery_id, max_attempts=max_attempts,
        next_retry_at=datetime.now(UTC) + _next_retry_delay(0),
    )
    db.add(retry)
    await db.commit()
    await db.refresh(retry)
    return retry


async def list_retries(
    db: AsyncSession, organization_id: int,
    status: str | None = None, webhook_id: int | None = None, limit: int = 50,
) -> list[WebhookRetry]:
    q = select(WebhookRetry).where(WebhookRetry.organization_id == organization_id)
    if status:
        q = q.where(WebhookRetry.status == status)
    if webhook_id:
        q = q.where(WebhookRetry.webhook_id == webhook_id)
    result = await db.execute(q.order_by(WebhookRetry.next_retry_at).limit(limit))
    return list(result.scalars().all())


async def get_pending_retries(
    db: AsyncSession, organization_id: int,
) -> list[WebhookRetry]:
    """Get retries that are due for execution."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(WebhookRetry).where(
            WebhookRetry.organization_id == organization_id,
            WebhookRetry.status.in_(["pending", "retrying"]),
            WebhookRetry.next_retry_at <= now,
        ).order_by(WebhookRetry.next_retry_at).limit(50)
    )
    return list(result.scalars().all())


async def mark_retry_result(
    db: AsyncSession, retry_id: int, success: bool, error: str | None = None,
) -> WebhookRetry | None:
    result = await db.execute(select(WebhookRetry).where(WebhookRetry.id == retry_id))
    retry = result.scalar_one_or_none()
    if not retry:
        return None
    if success:
        retry.status = "success"
    else:
        retry.attempt_count += 1
        retry.last_error = error
        if retry.attempt_count >= retry.max_attempts:
            retry.status = "exhausted"
        else:
            retry.status = "retrying"
            retry.next_retry_at = datetime.now(UTC) + _next_retry_delay(retry.attempt_count)
    await db.commit()
    await db.refresh(retry)
    return retry


async def get_retry_stats(db: AsyncSession, organization_id: int) -> dict:
    items = await list_retries(db, organization_id, limit=1000)
    by_status: dict[str, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    return {"total": len(items), "by_status": by_status}
