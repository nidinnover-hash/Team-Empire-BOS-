from sqlalchemy.ext.asyncio import AsyncSession

from app.core.privacy import sanitize_audit_payload
from app.models.event import Event
from app.schemas.event import EventCreate
from app.services import event as event_service

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
    return await event_service.log_event(
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
