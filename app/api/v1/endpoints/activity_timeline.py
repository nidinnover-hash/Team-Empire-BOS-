"""Global activity timeline — unified chronological feed across all entities."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.event import Event
from app.models.user import User

router = APIRouter(prefix="/activity", tags=["Activity Timeline"])


@router.get("/timeline")
async def get_activity_timeline(
    days: int = Query(7, ge=1, le=90),
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Unified activity feed with optional entity filtering."""
    org_id = int(actor["org_id"])
    since = datetime.now(UTC) - timedelta(days=days)

    q = (
        select(Event, User.name, User.email)
        .outerjoin(User, User.id == Event.actor_user_id)
        .where(Event.organization_id == org_id, Event.created_at >= since)
    )
    if entity_type:
        q = q.where(Event.entity_type == entity_type)
    if entity_id:
        q = q.where(Event.entity_id == entity_id)

    q = q.order_by(Event.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    rows = result.all()

    events = []
    for event, user_name, user_email in rows:
        events.append({
            "id": event.id,
            "event_type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "actor_user_id": event.actor_user_id,
            "actor_name": user_name,
            "actor_email": user_email,
            "payload": event.payload_json,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        })

    # Summary counts by entity type
    count_q = (
        select(Event.entity_type, func.count(Event.id))
        .where(Event.organization_id == org_id, Event.created_at >= since)
        .group_by(Event.entity_type)
    )
    count_result = await db.execute(count_q)
    entity_counts = {r[0] or "unknown": r[1] for r in count_result}

    return {
        "days": days,
        "total_in_period": sum(entity_counts.values()),
        "entity_counts": entity_counts,
        "events": events,
    }
