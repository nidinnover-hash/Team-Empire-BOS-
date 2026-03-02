import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.privacy import sanitize_audit_payload
from app.models.event import Event
from app.schemas.event import EventCreate
from app.services import event as event_service

logger = logging.getLogger(__name__)

_HIGH_RISK = {
    "execution_started", "send_message_sent", "integration_deleted",
    "user_role_changed", "approval_executed",
}
_MEDIUM_RISK = {
    "approval_requested", "integration_connected", "execution_failed",
    "approval_approved", "approval_rejected",
}


def _classify_risk(event_type: str) -> str:
    if event_type in _HIGH_RISK:
        return "high"
    if event_type in _MEDIUM_RISK:
        return "medium"
    return "low"


async def record_action(
    db: AsyncSession,
    event_type: str,
    actor_user_id: int | None,
    organization_id: int,
    entity_type: str | None = None,
    entity_id: int | None = None,
    payload_json: dict | None = None,
) -> Event:
    payload_with_risk = {**(payload_json or {}), "risk_level": _classify_risk(event_type)}
    safe_payload = sanitize_audit_payload(payload_with_risk)
    event = await event_service.log_event(
        db,
        EventCreate(
            organization_id=organization_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=safe_payload,
        ),
    )

    # Fire matching automation triggers (best-effort, inline).
    # The trigger query is now filtered by source_event in SQL for efficiency.
    try:
        from app.services.automation import fire_matching_triggers

        await fire_matching_triggers(
            db,
            organization_id=organization_id,
            event_type=event_type,
            event_payload=safe_payload,
        )
    except (ImportError, RuntimeError, ValueError, TypeError, OSError, AttributeError) as exc:
        logger.debug("Automation trigger matching failed for %s: %s", event_type, type(exc).__name__, exc_info=True)

    # Dispatch to registered webhook endpoints (best-effort).
    # Webhook HTTP delivery uses WEBHOOK_ASYNC_DISPATCH_ONLY for queue-based dispatch.
    try:
        from app.services.webhook import trigger_org_webhooks

        await trigger_org_webhooks(
            db,
            organization_id=organization_id,
            event=event_type,
            payload={
                "event": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                **(safe_payload or {}),
            },
        )
    except (ImportError, RuntimeError, ValueError, TypeError, OSError, AttributeError) as exc:
        logger.debug("Webhook dispatch failed for %s: %s", event_type, type(exc).__name__, exc_info=True)

    return event
