"""Lead routing — assign owner and SLA for new leads. BOS is the source of truth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lead_routing import LEAD_TYPE_ROUTE_MAP, normalize_lead_type
from app.models.user import User

RECRUITER_ROLES = ("CEO", "ADMIN", "MANAGER", "STAFF", "OWNER", "OPS_MANAGER")
DEFAULT_SLA_HOURS = 24


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
    Other systems must call BOS before assigning ownership.
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
            "sla_deadline_utc": None,
            "allowed": False,
            "reason": "No active users in organization for lead ownership.",
        }
    # Deterministic by lead_type + org for stable assignment
    key = f"{organization_id}:{normalize_lead_type(lead_type)}"
    idx = hash(key) % len(users)
    if idx < 0:
        idx += len(users)
    owner = users[idx]
    deadline = datetime.now(UTC) + timedelta(hours=DEFAULT_SLA_HOURS)
    return {
        "owner_user_id": owner.id,
        "owner_email": owner.email,
        "queue_id": None,
        "sla_deadline_utc": deadline.isoformat(),
        "allowed": True,
        "reason": None,
    }
