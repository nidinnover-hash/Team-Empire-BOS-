from __future__ import annotations

import hmac
import json
import logging
from hashlib import sha256

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.integrations_shared import safe_provider_error
from app.core.config import settings
from app.core.deps import get_db
from app.core.oauth_nonce import consume_oauth_nonce_once, oauth_nonce_seen
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import WhatsAppSendRequest, WhatsAppSendResult
from app.services import integration as integration_service
from app.services import whatsapp_service
from app.tools.whatsapp_business import get_phone_number_details, send_text_message

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Integrations"])


def _first_phone_number_id(payload: dict) -> str | None:
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if not isinstance(metadata, dict):
                continue
            raw_phone = metadata.get("phone_number_id")
            if isinstance(raw_phone, str) and raw_phone.strip():
                return raw_phone.strip()
    return None


async def _resolve_whatsapp_context(
    db: AsyncSession,
    payload: dict,
) -> tuple[int | None, int | None, str | None]:
    phone_number_id = _first_phone_number_id(payload)
    if not phone_number_id:
        return None, None, None
    integration = await integration_service.find_whatsapp_integration_by_phone_number_id(
        db,
        phone_number_id=phone_number_id,
    )
    if integration is None:
        return None, None, phone_number_id
    return int(integration.organization_id), int(integration.id), phone_number_id


@router.post("/whatsapp/send-test", response_model=WhatsAppSendResult)
async def whatsapp_send_test_message(
    data: WhatsAppSendRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WhatsAppSendResult:
    item = await integration_service.get_integration_by_type(
        db,
        organization_id=actor["org_id"],
        integration_type="whatsapp_business",
    )
    if item is None or item.status != "connected":
        raise HTTPException(status_code=400, detail="WhatsApp Business is not connected")
    if item.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Organization mismatch")

    access_token = item.config_json.get("access_token")
    phone_number_id = item.config_json.get("phone_number_id")
    if not access_token or not phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="Missing access_token or phone_number_id in whatsapp_business config_json",
        )
    try:
        resp = await send_text_message(
            access_token=str(access_token),
            phone_number_id=str(phone_number_id),
            to=data.to,
            body=data.body,
        )
    except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
        await record_action(
            db,
            event_type="whatsapp_test_message_failed",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=item.id,
            payload_json={
                "to": data.to,
                "error_code": "provider_send_failed",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=502,
            detail=safe_provider_error("WhatsApp message send failed"),
        ) from exc

    message_id: str | None = None
    messages = resp.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            raw_id = first.get("id")
            if isinstance(raw_id, str):
                message_id = raw_id
    await integration_service.mark_sync_time(db, item)
    await record_action(
        db,
        event_type="whatsapp_test_message_sent",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=item.id,
        payload_json={"to": data.to, "message_id": message_id},
    )
    return WhatsAppSendResult(status="queued", to=data.to, message_id=message_id)


@router.get("/whatsapp/webhook", include_in_schema=False)
async def whatsapp_webhook_verify(
    hub_mode: str | None = Query(None, alias="hub.mode", max_length=50),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token", max_length=500),
    hub_challenge: str | None = Query(None, alias="hub.challenge", max_length=5000),
) -> PlainTextResponse:
    expected = (settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "").strip()
    if (
        hub_mode == "subscribe"
        and hub_verify_token
        and expected
        and hmac.compare_digest(hub_verify_token, expected)
        and hub_challenge is not None
    ):
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp/webhook", include_in_schema=False)
async def whatsapp_webhook_receive(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.core.middleware import check_per_route_rate_limit, get_client_ip

    if not check_per_route_rate_limit(get_client_ip(request), "whatsapp_webhook", max_requests=60, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many webhook deliveries. Try again later.")

    max_webhook_body = 1_048_576
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_webhook_body:
                raise HTTPException(status_code=413, detail="Webhook payload too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc

    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        raise HTTPException(status_code=415, detail="Webhook expects application/json")

    raw_body = await request.body()
    if len(raw_body) > max_webhook_body:
        raise HTTPException(status_code=413, detail="Webhook payload too large")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object")

    app_secret = (settings.WHATSAPP_APP_SECRET or "").strip()
    if not app_secret:
        raise HTTPException(
            status_code=503,
            detail="WhatsApp webhook disabled: WHATSAPP_APP_SECRET not configured",
        )

    sig_header = request.headers.get("X-Hub-Signature-256", "")
    expected_sig = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        sha256,
    ).hexdigest()
    if not sig_header or not hmac.compare_digest(sig_header, expected_sig):
        wa_org_id, wa_integ_id, wa_phone = await _resolve_whatsapp_context(db, payload)
        if wa_org_id is not None:
            await record_action(
                db=db,
                event_type="whatsapp_webhook_failed",
                actor_user_id=None,
                organization_id=wa_org_id,
                entity_type="integration",
                entity_id=wa_integ_id,
                payload_json={
                    "error_code": "signature_verification_failed",
                    "detail": "X-Hub-Signature-256 mismatch",
                    "phone_number_id": wa_phone,
                },
            )
        raise HTTPException(status_code=403, detail="Webhook signature verification failed")

    window = max(30, int(settings.WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS))
    if oauth_nonce_seen(namespace="whatsapp_webhook_sig", nonce=sig_header, max_age_seconds=window):
        raise HTTPException(status_code=409, detail="Webhook replay detected")

    entries = payload.get("entry")
    count = len(entries) if isinstance(entries, list) else 0
    try:
        telemetry = await whatsapp_service.ingest_webhook_payload(db, payload)
    except Exception as exc:
        logger.warning("WhatsApp webhook ingest failed: %s", exc, exc_info=True)
        fail_org_id, fail_integ_id, fail_phone = await _resolve_whatsapp_context(db, payload)
        if fail_org_id is not None:
            await record_action(
                db=db,
                event_type="whatsapp_webhook_failed",
                actor_user_id=None,
                organization_id=fail_org_id,
                entity_type="integration",
                entity_id=fail_integ_id,
                payload_json={
                    "error_code": "ingest_error",
                    "detail": str(exc)[:500],
                    "phone_number_id": fail_phone,
                },
            )
        raise HTTPException(status_code=500, detail="Webhook processing failed") from exc

    if not consume_oauth_nonce_once(namespace="whatsapp_webhook_sig", nonce=sig_header, max_age_seconds=window):
        raise HTTPException(status_code=409, detail="Webhook replay detected")

    webhook_org_id, webhook_integration_id, webhook_phone_number_id = await _resolve_whatsapp_context(
        db,
        payload,
    )
    if webhook_org_id is not None:
        await record_action(
            db=db,
            event_type="whatsapp_webhook_received",
            actor_user_id=None,
            organization_id=webhook_org_id,
            entity_type="integration",
            entity_id=webhook_integration_id,
            payload_json={
                "entries": count,
                "phone_number_id": webhook_phone_number_id,
                **telemetry,
            },
        )
    return {"status": "received", "entries": count, **telemetry}


__all__ = [
    "_resolve_whatsapp_context",
    "get_phone_number_details",
    "send_text_message",
    "whatsapp_service",
]
