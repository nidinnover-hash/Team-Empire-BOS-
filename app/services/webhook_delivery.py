"""Webhook delivery log service — track delivery attempts and retries."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_delivery import OutboundWebhookDelivery


async def log_delivery(
    db: AsyncSession, organization_id: int, webhook_id: int,
    event_type: str, url: str, request_body: str | None = None,
    response_status: int | None = None, response_body: str | None = None,
    attempt_number: int = 1, status: str = "pending",
    error_message: str | None = None,
) -> OutboundWebhookDelivery:
    delivery = OutboundWebhookDelivery(
        organization_id=organization_id, webhook_id=webhook_id,
        event_type=event_type, url=url, request_body=request_body,
        response_status=response_status, response_body=response_body,
        attempt_number=attempt_number, status=status,
        error_message=error_message,
        completed_at=datetime.now(UTC) if status in ("success", "failed") else None,
    )
    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)
    return delivery


async def list_deliveries(
    db: AsyncSession, organization_id: int,
    webhook_id: int | None = None, status: str | None = None, limit: int = 50,
) -> list[OutboundWebhookDelivery]:
    q = select(OutboundWebhookDelivery).where(OutboundWebhookDelivery.organization_id == organization_id)
    if webhook_id:
        q = q.where(OutboundWebhookDelivery.webhook_id == webhook_id)
    if status:
        q = q.where(OutboundWebhookDelivery.status == status)
    result = await db.execute(q.order_by(OutboundWebhookDelivery.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def get_delivery_stats(
    db: AsyncSession, organization_id: int, webhook_id: int | None = None,
) -> dict:
    items = await list_deliveries(db, organization_id, webhook_id=webhook_id, limit=1000)
    by_status: dict[str, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    return {"total": len(items), "by_status": by_status}


async def mark_delivery_result(
    db: AsyncSession, delivery_id: int,
    response_status: int, response_body: str | None = None,
    status: str = "success", error_message: str | None = None,
) -> OutboundWebhookDelivery | None:
    result = await db.execute(
        select(OutboundWebhookDelivery).where(OutboundWebhookDelivery.id == delivery_id)
    )
    delivery = result.scalar_one_or_none()
    if not delivery:
        return None
    delivery.response_status = response_status
    delivery.response_body = response_body
    delivery.status = status
    delivery.error_message = error_message
    delivery.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(delivery)
    return delivery
