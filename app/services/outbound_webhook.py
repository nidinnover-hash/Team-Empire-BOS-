"""Outbound webhook service — manage and dispatch webhooks to external systems."""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbound_webhook import OutboundWebhook

logger = logging.getLogger(__name__)


async def create_webhook(
    db: AsyncSession, organization_id: int, **kwargs,
) -> OutboundWebhook:
    if "event_types" in kwargs:
        kwargs["event_types_json"] = json.dumps(kwargs.pop("event_types"))
    if "headers" in kwargs:
        kwargs["headers_json"] = json.dumps(kwargs.pop("headers"))
    wh = OutboundWebhook(organization_id=organization_id, **kwargs)
    db.add(wh)
    await db.commit()
    await db.refresh(wh)
    return wh


async def list_webhooks(
    db: AsyncSession, organization_id: int, active_only: bool = True,
) -> list[OutboundWebhook]:
    q = select(OutboundWebhook).where(
        OutboundWebhook.organization_id == organization_id,
    )
    if active_only:
        q = q.where(OutboundWebhook.is_active.is_(True))
    q = q.order_by(OutboundWebhook.id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_webhook(
    db: AsyncSession, webhook_id: int, organization_id: int, **kwargs,
) -> OutboundWebhook | None:
    result = await db.execute(
        select(OutboundWebhook).where(
            OutboundWebhook.id == webhook_id,
            OutboundWebhook.organization_id == organization_id,
        )
    )
    wh = result.scalar_one_or_none()
    if wh is None:
        return None
    if "event_types" in kwargs:
        kwargs["event_types_json"] = json.dumps(kwargs.pop("event_types"))
    if "headers" in kwargs:
        kwargs["headers_json"] = json.dumps(kwargs.pop("headers"))
    for k, v in kwargs.items():
        if v is not None and hasattr(wh, k):
            setattr(wh, k, v)
    await db.commit()
    await db.refresh(wh)
    return wh


async def delete_webhook(
    db: AsyncSession, webhook_id: int, organization_id: int,
) -> bool:
    result = await db.execute(
        select(OutboundWebhook).where(
            OutboundWebhook.id == webhook_id,
            OutboundWebhook.organization_id == organization_id,
        )
    )
    wh = result.scalar_one_or_none()
    if wh is None:
        return False
    await db.delete(wh)
    await db.commit()
    return True


def match_event(event_type: str, webhook: OutboundWebhook) -> bool:
    """Check if an event type matches a webhook's configured patterns."""
    patterns = json.loads(webhook.event_types_json) if webhook.event_types_json else ["*"]
    return any(fnmatch.fnmatch(event_type, p) for p in patterns)


async def get_matching_webhooks(
    db: AsyncSession, organization_id: int, event_type: str,
) -> list[OutboundWebhook]:
    """Find all active webhooks that match a given event type."""
    webhooks = await list_webhooks(db, organization_id, active_only=True)
    return [wh for wh in webhooks if match_event(event_type, wh)]


def build_payload(event_type: str, data: dict, secret: str | None = None) -> dict:
    """Build a webhook payload with optional HMAC signature."""
    payload = {
        "event": event_type,
        "data": data,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if secret:
        body = json.dumps(payload, sort_keys=True)
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        payload["signature"] = signature
    return payload
