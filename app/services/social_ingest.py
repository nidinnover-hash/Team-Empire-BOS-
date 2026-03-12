"""Social lead ingest: create/merge contact in Empire Digital, route lead, emit signal."""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lead_routing import EMPIRE_DIGITAL_COMPANY_ID, normalize_lead_type
from app.platform.signals import (
    LEAD_CREATED_FROM_SOCIAL,
    SignalCategory,
    SignalEnvelope,
    publish_signal,
)
from app.schemas.contact import ContactCreate
from app.schemas.lead_ingest import SocialLeadIngestRequest, SocialLeadIngestResponse
from app.services import contact as contact_service
from app.services import lead_routing_service as routing_service

logger = logging.getLogger(__name__)


def _safe_email(value: str | None) -> str | None:
    """Return value if it looks like an email; otherwise None (for ContactCreate)."""
    if not value or not value.strip():
        return None
    s = value.strip()
    if "@" in s and "." in s and len(s) <= 500:
        return s
    return None


async def ingest_social_lead(
    db: AsyncSession,
    data: SocialLeadIngestRequest,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
) -> SocialLeadIngestResponse:
    """
    Find or create contact in Empire Digital org, run route_lead, set routing fields, emit lead.created_from_social.
    Caller must ensure organization_id == EMPIRE_DIGITAL_COMPANY_ID.
    """
    if organization_id != EMPIRE_DIGITAL_COMPANY_ID:
        raise ValueError("Social ingest is only allowed for Empire Digital organization")

    email = _safe_email(data.email)
    contact = await contact_service.find_contact_by_email_or_phone(
        db, organization_id, email=data.email, phone=data.phone
    )
    created = False
    if contact is None:
        campaign = (data.utm or {}).get("campaign") if data.utm else None
        campaign_name = (campaign or data.brand_slug or "")[:200] or None
        create_payload = ContactCreate(
            name=data.full_name.strip(),
            email=email,
            phone=(data.phone or "").strip() or None,
            notes=(data.message or "")[:2000] or None,
            lead_source="social_media",
            source_channel=(data.source_platform or "social")[:80],
            campaign_name=campaign_name,
            lead_type=normalize_lead_type(data.lead_type or "general"),
        )
        contact = await contact_service.create_contact(db, create_payload, organization_id)
        created = True

    routing = await routing_service.route_lead(
        db,
        organization_id,
        lead_type=normalize_lead_type(data.lead_type or "general"),
        region=data.region,
        source=data.source_platform or data.brand_slug,
        payload=data.raw_payload,
    )
    routed = bool(routing.get("allowed") and routing.get("owner_user_id"))
    next_follow_up = None
    if routing.get("sla_deadline_utc"):
        with contextlib.suppress(ValueError, TypeError):
            next_follow_up = datetime.fromisoformat(routing["sla_deadline_utc"].replace("Z", "+00:00"))
    contact.routed_by_user_id = routing.get("owner_user_id")
    contact.routed_at = datetime.now(UTC) if routed else None
    contact.routing_status = "routed" if routed else "unrouted"
    contact.routing_reason = routing.get("reason") or ("social_ingest" if routed else "no_owner")
    contact.routing_source = "rule" if routed else "default"
    contact.next_follow_up_at = next_follow_up
    await db.commit()
    await db.refresh(contact)

    payload = {
        "contact_id": contact.id,
        "created": created,
        "source_platform": data.source_platform,
        "page_id": data.page_id,
        "brand_slug": data.brand_slug,
        "lead_type": data.lead_type,
        "region": data.region,
        "owner_user_id": routing.get("owner_user_id"),
        "sla_deadline_utc": routing.get("sla_deadline_utc"),
    }
    await publish_signal(
        SignalEnvelope(
            topic=LEAD_CREATED_FROM_SOCIAL,
            category=SignalCategory.DOMAIN,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            source="social_ingest",
            entity_type="contact",
            entity_id=str(contact.id),
            payload=payload,
        ),
        db=db,
    )
    logger.info(
        "social_ingest contact_id=%s created=%s routed=%s",
        contact.id, created, routed,
    )
    return SocialLeadIngestResponse(
        contact_id=contact.id,
        created=created,
        routed=routed,
        owner_user_id=routing.get("owner_user_id"),
        sla_deadline_utc=routing.get("sla_deadline_utc"),
    )
