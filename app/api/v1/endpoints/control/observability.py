"""Control observability — report on control lever usage from audit events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.event import Event
from app.models.organization import Organization

router = APIRouter(prefix="/observability", tags=["Control Observability"])

CONTROL_EVENT_TYPES = (
    "placement_confirmed",
    "money_approval_requested",
)


class ControlObservabilityReport(BaseModel):
    by_event_type: list[dict]
    by_organization: list[dict]
    window_start: str
    window_end: str


@router.get("/control-report", response_model=ControlObservabilityReport)
async def control_report(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ControlObservabilityReport:
    """
    Report on control lever usage: counts of placement_confirmed and
    money_approval_requested by event_type and by organization (last 7 days).
    Use for observability and capacity planning. by_organization includes org slug.
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(days=7)

    by_type_result = await db.execute(
        select(Event.event_type, func.count(Event.id).label("count"))
        .where(
            Event.created_at >= window_start,
            Event.event_type.in_(CONTROL_EVENT_TYPES),
        )
        .group_by(Event.event_type)
    )
    by_event_type = [
        {"event_type": row.event_type, "count": row.count}
        for row in by_type_result.all()
    ]

    by_org_result = await db.execute(
        select(Event.organization_id, Event.event_type, func.count(Event.id).label("count"))
        .where(
            Event.created_at >= window_start,
            Event.event_type.in_(CONTROL_EVENT_TYPES),
        )
        .group_by(Event.organization_id, Event.event_type)
    )
    rows = by_org_result.all()
    org_ids = list({r.organization_id for r in rows})
    org_slugs: dict[int, str] = {}
    if org_ids:
        org_result = await db.execute(
            select(Organization.id, Organization.slug).where(Organization.id.in_(org_ids))
        )
        for o in org_result.all():
            org_slugs[o.id] = o.slug or str(o.id)
    by_organization = [
        {
            "organization_id": row.organization_id,
            "organization_slug": org_slugs.get(row.organization_id, str(row.organization_id)),
            "event_type": row.event_type,
            "count": row.count,
        }
        for row in rows
    ]

    return ControlObservabilityReport(
        by_event_type=by_event_type,
        by_organization=by_organization,
        window_start=window_start.isoformat(),
        window_end=now.isoformat(),
    )
