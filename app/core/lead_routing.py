"""Lead routing policy helpers for cross-company lead flow."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import and_, or_

from app.models.contact import Contact

logger = logging.getLogger(__name__)

LEAD_ROUTING_STATUSES = ("unrouted", "under_review", "routed", "accepted", "rejected", "closed")
LEAD_TYPES = ("general", "study_abroad", "recruitment")

# Empire Digital is the default lead owner company in Team Empire.
EMPIRE_DIGITAL_COMPANY_ID = 1

# Route-map by lead type for automatic routing.
LEAD_TYPE_ROUTE_MAP: dict[str, int] = {
    "study_abroad": 2,  # ESA.ai
    "recruitment": 3,   # EmpireO.ai
}

LEAD_ROUTING_TRANSITIONS: dict[str, set[str]] = {
    "unrouted": {"under_review", "routed", "closed"},
    "under_review": {"routed", "rejected", "closed"},
    "routed": {"accepted", "rejected", "closed"},
    "accepted": {"closed"},
    "rejected": {"closed"},
    "closed": set(),
}


def normalize_lead_type(value: object) -> str:
    lead_type = str(value or "general").strip().lower()
    return lead_type if lead_type in LEAD_TYPES else "general"


def normalize_routing_status(value: object) -> str:
    status = str(value or "unrouted").strip().lower()
    return status if status in LEAD_ROUTING_STATUSES else "unrouted"


def is_valid_routing_transition(current_status: object, next_status: object) -> bool:
    current = normalize_routing_status(current_status)
    nxt = normalize_routing_status(next_status)
    if current == nxt:
        return True
    return nxt in LEAD_ROUTING_TRANSITIONS.get(current, set())


def resolve_routed_company_id(*, lead_type: object, manual_company_id: int | None) -> tuple[int | None, str]:
    if manual_company_id is not None:
        return int(manual_company_id), "routed"
    target = LEAD_TYPE_ROUTE_MAP.get(normalize_lead_type(lead_type))
    if target is None:
        return None, "unrouted"
    return int(target), "routed"


def apply_contact_visibility_scope(
    query,
    *,
    actor_org_id: int,
    actor_role: object,
    actor_id: int | None = None,
):
    """Apply lead visibility scope for an actor across company boundaries.

    - CEO: full visibility.
    - Empire Digital users (org=EMPIRE_DIGITAL_COMPANY_ID): all empire-owned leads.
    - Service company users: only leads routed to their company.
    """
    role = str(actor_role or "").upper()
    actor_org_id = int(actor_org_id)
    if role == "CEO" and actor_org_id == EMPIRE_DIGITAL_COMPANY_ID:
        logger.info(
            "CEO cross-org full access granted actor_id=%s org_id=%s",
            actor_id,
            actor_org_id,
        )
        return query
    if role == "ADMIN" and actor_org_id == EMPIRE_DIGITAL_COMPANY_ID:
        return query.where(
            or_(
                Contact.lead_owner_company_id == EMPIRE_DIGITAL_COMPANY_ID,
                Contact.organization_id == EMPIRE_DIGITAL_COMPANY_ID,
            )
        )
    # Managers/Staff and non-empire admins see only company-local leads:
    # - leads explicitly routed to their company
    # - leads owned by their company and not routed away
    return query.where(
        or_(
            Contact.routed_company_id == actor_org_id,
            and_(
                Contact.lead_owner_company_id == actor_org_id,
                Contact.routed_company_id.is_(None),
            ),
        )
    )


def now_utc() -> datetime:
    return datetime.now(UTC)
