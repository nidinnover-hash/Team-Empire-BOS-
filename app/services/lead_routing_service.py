"""Lead routing — assign owner and SLA for new leads. BOS is the source of truth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lead_routing import normalize_lead_type
from app.models.recruitment_routing_rule import RecruitmentRoutingRule
from app.models.user import User
from app.services import organization as organization_service

RECRUITER_ROLES = ("CEO", "ADMIN", "MANAGER", "STAFF", "OWNER", "OPS_MANAGER")
DEFAULT_SLA_HOURS = 24


def _sla_hours_from_policy(policy: dict) -> int:
    """Lead SLA hours from org policy (empire_digital.sla.lead_sla_hours or default)."""
    try:
        ed = policy.get("empire_digital") or {}
        sla = ed.get("sla") or {}
        h = sla.get("lead_sla_hours")
        if h is not None:
            return max(1, int(h))
    except (TypeError, ValueError):
        pass
    return DEFAULT_SLA_HOURS


async def route_lead(
    db: AsyncSession,
    organization_id: int,
    *,
    lead_type: str = "general",
    region: str | None = None,
    source: str | None = None,
    payload: dict | None = None,
) -> dict:
    """
    Return owner_user_id, queue_id, sla_deadline_utc for a new lead.
    Uses RecruitmentRoutingRule by region/product_line when provided; else deterministic hash by lead_type.
    SLA from org policy (empire_digital.sla.lead_sla_hours) or default.
    """
    policy = await organization_service.get_policy_config(db, organization_id)
    sla_hours = _sla_hours_from_policy(policy)

    region_norm = (region or "").strip().lower() or None
    product_norm = (source or "").strip().lower() or None
    lead_type_norm = normalize_lead_type(lead_type) if lead_type else None

    rules_result = await db.execute(
        select(RecruitmentRoutingRule)
        .where(RecruitmentRoutingRule.organization_id == organization_id)
        .order_by(RecruitmentRoutingRule.priority.desc(), RecruitmentRoutingRule.id)
    )
    rules = list(rules_result.scalars().all())
    for rule in rules:
        r_region = (rule.region or "").strip().lower() or None
        r_product = (rule.product_line or "").strip().lower() or None
        r_lead = (getattr(rule, "lead_type", None) or "").strip().lower() or None
        if r_region and region_norm and r_region != region_norm:
            continue
        if r_product and product_norm and r_product != product_norm:
            continue
        if r_lead and lead_type_norm and r_lead != lead_type_norm:
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
                rule_sla = getattr(rule, "sla_hours", None)
                hours = max(1, int(rule_sla)) if rule_sla is not None else sla_hours
                deadline = datetime.now(UTC) + timedelta(hours=hours)
                return {
                    "owner_user_id": owner.id,
                    "owner_email": owner.email,
                    "queue_id": None,
                    "sla_deadline_utc": deadline.isoformat(),
                    "allowed": True,
                    "reason": None,
                }
        break

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
            "sla_deadline_utc": None,
            "allowed": False,
            "reason": "No active users in organization for lead ownership.",
        }
    key = f"{organization_id}:{normalize_lead_type(lead_type)}"
    idx = hash(key) % len(users)
    if idx < 0:
        idx += len(users)
    owner = users[idx]
    deadline = datetime.now(UTC) + timedelta(hours=sla_hours)
    return {
        "owner_user_id": owner.id,
        "owner_email": owner.email,
        "queue_id": None,
        "sla_deadline_utc": deadline.isoformat(),
        "allowed": True,
        "reason": None,
    }
