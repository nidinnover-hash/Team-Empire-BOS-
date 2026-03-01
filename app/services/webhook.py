from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.token_crypto import decrypt_token, encrypt_token
from app.models.webhook import WebhookDelivery, WebhookEndpoint
from app.schemas.webhook import VALID_WEBHOOK_EVENTS

logger = logging.getLogger(__name__)

_DISPATCH_TIMEOUT_SECONDS = 10.0
_MAX_DELIVERIES_PER_ENDPOINT = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_signing_secret() -> str:
    return secrets.token_hex(32)


def _compute_signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Webhook URL must include a hostname")
    if host in {"localhost", "0.0.0.0"} or host.endswith(".localhost"):
        raise ValueError("Webhook URL host is not allowed")
    if host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Webhook URL host is not allowed")
    if not settings.DEBUG and not url.startswith("https://"):
        raise ValueError("Webhook URL must use HTTPS in production")
    if not url.startswith(("http://", "https://")):
        raise ValueError("Webhook URL must start with http:// or https://")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        raise ValueError("Webhook URL host is not allowed")


def _validate_event_types(event_types: list[str]) -> None:
    for et in event_types:
        if et not in VALID_WEBHOOK_EVENTS:
            raise ValueError(f"Unknown event type: {et}")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_webhook_endpoint(
    db: AsyncSession,
    *,
    organization_id: int,
    url: str,
    description: str | None = None,
    event_types: list[str] | None = None,
) -> tuple[WebhookEndpoint, str]:
    """Create a webhook endpoint. Returns (endpoint, plaintext_secret)."""
    _validate_url(url)
    events = event_types or []
    if events:
        _validate_event_types(events)
    plaintext_secret = _generate_signing_secret()
    endpoint = WebhookEndpoint(
        organization_id=organization_id,
        url=url,
        description=description,
        secret_encrypted=encrypt_token(plaintext_secret),
        event_types=events,
        is_active=True,
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return endpoint, plaintext_secret


async def list_webhook_endpoints(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[WebhookEndpoint]:
    result = await db.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.organization_id == organization_id)
        .order_by(WebhookEndpoint.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_webhook_endpoint(
    db: AsyncSession,
    endpoint_id: int,
    organization_id: int,
) -> WebhookEndpoint | None:
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id,
            WebhookEndpoint.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_webhook_endpoint(
    db: AsyncSession,
    endpoint_id: int,
    organization_id: int,
    **fields: Any,
) -> WebhookEndpoint | None:
    endpoint = await get_webhook_endpoint(db, endpoint_id, organization_id)
    if endpoint is None:
        return None
    if "url" in fields and fields["url"] is not None:
        _validate_url(fields["url"])
        endpoint.url = fields["url"]
    if "description" in fields:
        endpoint.description = fields["description"]
    if "event_types" in fields and fields["event_types"] is not None:
        _validate_event_types(fields["event_types"])
        endpoint.event_types = fields["event_types"]
    if "is_active" in fields and fields["is_active"] is not None:
        endpoint.is_active = fields["is_active"]
    await db.commit()
    await db.refresh(endpoint)
    return endpoint


async def delete_webhook_endpoint(
    db: AsyncSession,
    endpoint_id: int,
    organization_id: int,
) -> bool:
    endpoint = await get_webhook_endpoint(db, endpoint_id, organization_id)
    if endpoint is None:
        return False
    await db.delete(endpoint)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Delivery log
# ---------------------------------------------------------------------------


async def list_deliveries(
    db: AsyncSession,
    endpoint_id: int,
    organization_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[WebhookDelivery]:
    result = await db.execute(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.webhook_endpoint_id == endpoint_id,
            WebhookDelivery.organization_id == organization_id,
        )
        .order_by(WebhookDelivery.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def _prune_old_deliveries(db: AsyncSession, endpoint_id: int) -> None:
    count_result = await db.execute(
        select(func.count(WebhookDelivery.id)).where(
            WebhookDelivery.webhook_endpoint_id == endpoint_id
        )
    )
    total = int(count_result.scalar_one() or 0)
    if total <= _MAX_DELIVERIES_PER_ENDPOINT:
        return
    cutoff_result = await db.execute(
        select(WebhookDelivery.id)
        .where(WebhookDelivery.webhook_endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.created_at.desc())
        .offset(_MAX_DELIVERIES_PER_ENDPOINT)
        .limit(1)
    )
    cutoff_id = cutoff_result.scalar_one_or_none()
    if cutoff_id is not None:
        await db.execute(
            delete(WebhookDelivery).where(
                WebhookDelivery.webhook_endpoint_id == endpoint_id,
                WebhookDelivery.id <= cutoff_id,
            )
        )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def _dispatch_to_endpoint(
    db: AsyncSession,
    endpoint: WebhookEndpoint,
    event: str,
    payload: dict[str, Any],
) -> WebhookDelivery:
    body_bytes = json.dumps(payload, default=str).encode("utf-8")
    secret = decrypt_token(endpoint.secret_encrypted)
    signature = _compute_signature(secret, body_bytes)

    delivery = WebhookDelivery(
        webhook_endpoint_id=endpoint.id,
        organization_id=endpoint.organization_id,
        event=event,
        payload_json=payload,
        status="pending",
        attempt_count=1,
    )
    db.add(delivery)

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_DISPATCH_TIMEOUT_SECONDS) as client:
            response = await client.post(
                endpoint.url,
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Event": event,
                    "X-Webhook-Signature-256": signature,
                    "User-Agent": "NidinNoverAI-Webhook/1.0",
                },
            )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        delivery.response_status_code = response.status_code
        delivery.duration_ms = elapsed_ms
        if 200 <= response.status_code < 300:
            delivery.status = "success"
        else:
            delivery.status = "failed"
            delivery.error_message = f"HTTP {response.status_code}"
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        delivery.status = "failed"
        delivery.duration_ms = elapsed_ms
        delivery.error_message = f"{type(exc).__name__}: {str(exc)[:500]}"
        logger.warning(
            "Webhook dispatch failed endpoint_id=%d url=%s event=%s: %s",
            endpoint.id,
            endpoint.url,
            event,
            type(exc).__name__,
        )

    await db.commit()
    await db.refresh(delivery)

    try:
        await _prune_old_deliveries(db, endpoint.id)
        await db.commit()
    except Exception:
        logger.debug("Delivery pruning failed", exc_info=True)

    return delivery


async def trigger_org_webhooks(
    db: AsyncSession,
    *,
    organization_id: int,
    event: str,
    payload: dict[str, Any],
) -> None:
    """Dispatch event to all active webhook endpoints subscribed to it."""
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == organization_id,
            WebhookEndpoint.is_active.is_(True),
        )
    )
    endpoints = list(result.scalars().all())

    for endpoint in endpoints:
        subscribed = endpoint.event_types or []
        if subscribed and event not in subscribed:
            continue
        try:
            await _dispatch_to_endpoint(db, endpoint, event, payload)
        except Exception as exc:
            logger.warning(
                "Webhook dispatch error endpoint_id=%d: %s",
                endpoint.id,
                type(exc).__name__,
            )


async def send_test_webhook(
    db: AsyncSession,
    endpoint_id: int,
    organization_id: int,
) -> dict[str, Any]:
    endpoint = await get_webhook_endpoint(db, endpoint_id, organization_id)
    if endpoint is None:
        return {"ok": False, "error": "Webhook endpoint not found"}

    test_payload = {
        "event": "webhook.test",
        "message": "This is a test delivery from Nidin BOS",
        "webhook_endpoint_id": endpoint.id,
    }
    delivery = await _dispatch_to_endpoint(db, endpoint, "webhook.test", test_payload)
    return {
        "ok": delivery.status == "success",
        "status_code": delivery.response_status_code,
        "error": delivery.error_message,
        "duration_ms": delivery.duration_ms,
    }
