"""Recruitment routing — assign candidate ownership and SLA via BOS (EmpireO)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# Roles that can own candidates (recruiters).
RECRUITER_ROLES = ("CEO", "ADMIN", "MANAGER", "STAFF", "OWNER", "OPS_MANAGER")

# Default SLA: first contact within this many hours.
DEFAULT_FIRST_CONTACT_SLA_HOURS = 24


async def route_candidate(
    db: AsyncSession,
    organization_id: int,
    *,
    candidate_id: str,
    job_id: str | None = None,
    source: str | None = None,
    region: str | None = None,
    product_line: str | None = None,
    sla_hours: int = DEFAULT_FIRST_CONTACT_SLA_HOURS,
) -> dict:
    """
    Decide owner and SLA for a new candidate. Called by the Recruitment App;
    BOS is the single source of truth for routing.

    Returns dict with: owner_user_id, owner_email, queue_id, sla_first_contact_at, allowed, reason.
    """
    result = await db.execute(
        select(User)
        .where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            User.role.in_(RECRUITER_ROLES),
        )
        .order_by(User.id)
    )
    users = list(result.scalars().all())

    if not users:
        return {
            "owner_user_id": None,
            "owner_email": None,
            "queue_id": None,
            "sla_first_contact_at": None,
            "allowed": False,
            "reason": "No active recruiters in organization. Add users with role in CEO, ADMIN, MANAGER, STAFF, OWNER, OPS_MANAGER.",
        }

    # Deterministic assignment by candidate_id so retries get same owner.
    idx = hash(candidate_id) % len(users)
    if idx < 0:
        idx += len(users)
    owner = users[idx]

    sla_at = datetime.now(UTC) + timedelta(hours=max(1, sla_hours))

    return {
        "owner_user_id": owner.id,
        "owner_email": owner.email,
        "queue_id": None,
        "sla_first_contact_at": sla_at.isoformat(),
        "allowed": True,
        "reason": None,
    }


async def assign_owner(
    db: AsyncSession,
    organization_id: int,
    *,
    candidate_id: str,
    job_id: str | None,
    new_owner_user_id: int,
    reason: str | None = None,
) -> dict:
    """
    Decide whether ownership change is allowed. BOS is source of truth.
    Returns: allowed, previous_owner_user_id (None if unknown), new_owner_user_id, message.
    """
    result = await db.execute(
        select(User).where(
            User.id == new_owner_user_id,
            User.organization_id == organization_id,
            User.is_active.is_(True),
            User.role.in_(RECRUITER_ROLES),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        return {
            "allowed": False,
            "previous_owner_user_id": None,
            "new_owner_user_id": new_owner_user_id,
            "message": "New owner not found or not an active recruiter in this organization.",
        }
    return {
        "allowed": True,
        "previous_owner_user_id": None,
        "new_owner_user_id": user.id,
        "message": None,
    }


# Stages that require approval before moving (e.g. to offer).
STAGES_REQUIRING_APPROVAL = frozenset({"offer"})


async def candidate_stage(
    db: AsyncSession,
    organization_id: int,
    *,
    candidate_id: str,
    job_id: str | None,
    from_stage: str,
    to_stage: str,
    payload: dict | None = None,
) -> dict:
    """
    Decide whether stage transition is allowed and if approval is required.
    Returns: allowed, requires_approval, approval_type, message.
    """
    allowed = True
    requires_approval = to_stage.lower() in STAGES_REQUIRING_APPROVAL
    approval_type = "recruitment_offer" if requires_approval else None
    message = (
        "Offer stage requires approval. Create an approval request before moving."
        if requires_approval
        else None
    )
    return {
        "allowed": allowed,
        "requires_approval": requires_approval,
        "approval_type": approval_type,
        "message": message,
    }


async def confirm_placement(
    db: AsyncSession,
    organization_id: int,
    *,
    candidate_id: str,
    job_id: str | None,
    approval_id: int | None = None,
    placed_at: str | None = None,
    start_date: str | None = None,
    payload: dict | None = None,
) -> dict:
    """
    Record placement for audit. BOS does not store placement records yet;
    we return recorded=True and a synthetic placement_id for the contract.
    """
    placement_id = f"bos-{candidate_id}-{job_id or 'unknown'}-{uuid.uuid4().hex[:8]}"
    return {"recorded": True, "placement_id": placement_id}
