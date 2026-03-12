"""Recruitment routing — assign candidate ownership and SLA via BOS (EmpireO)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recruitment_placement import RecruitmentPlacement
from app.models.recruitment_routing_rule import RecruitmentRoutingRule
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
    Decide owner and SLA using configurable rules (region/product_line) or fallback to hash.
    Returns dict with: owner_user_id, owner_email, queue_id, sla_first_contact_at, allowed, reason.
    """
    # Load rules for org (higher priority first)
    rules_result = await db.execute(
        select(RecruitmentRoutingRule)
        .where(RecruitmentRoutingRule.organization_id == organization_id)
        .order_by(RecruitmentRoutingRule.priority.desc(), RecruitmentRoutingRule.id)
    )
    rules = list(rules_result.scalars().all())

    region_norm = (region or "").strip().lower() or None
    product_norm = (product_line or "").strip().lower() or None

    for rule in rules:
        r_region = (rule.region or "").strip().lower() or None
        r_product = (rule.product_line or "").strip().lower() or None
        if r_region and region_norm and r_region != region_norm:
            continue
        if r_product and product_norm and r_product != product_norm:
            continue
        if rule.assign_to_user_id:
            user_result = await db.execute(
                select(User).where(
                    User.id == rule.assign_to_user_id,
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                    User.role.in_(RECRUITER_ROLES),
                )
            )
            owner = user_result.scalar_one_or_none()
            if owner:
                sla_at = datetime.now(UTC) + timedelta(hours=max(1, sla_hours))
                return {
                    "owner_user_id": owner.id,
                    "owner_email": owner.email,
                    "queue_id": None,
                    "sla_first_contact_at": sla_at.isoformat(),
                    "allowed": True,
                    "reason": None,
                }
        break

    # Fallback: all recruiters, deterministic by candidate_id
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


def _parse_placed_at(placed_at: str | None) -> datetime | None:
    if not placed_at:
        return None
    try:
        return datetime.fromisoformat(placed_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


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
    Persist placement and return recorded=True and placement_id (BOS id).
    """
    now = datetime.now(UTC)
    placed_dt = _parse_placed_at(placed_at) or now
    payload_json = dict(payload or {})
    row = RecruitmentPlacement(
        organization_id=organization_id,
        candidate_id=candidate_id,
        job_id=job_id,
        approval_id=approval_id,
        placed_at=placed_dt,
        start_date=start_date,
        payload_json=payload_json,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"recorded": True, "placement_id": str(row.id)}
