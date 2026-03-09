"""Contact activity timeline — aggregates events, deals, and notes for a contact."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal
from app.models.event import Event
from app.models.note import Note


async def get_contact_timeline(
    db: AsyncSession,
    contact_id: int,
    organization_id: int,
    limit: int = 50,
) -> list[dict]:
    """Build a unified timeline of activity for a single contact."""
    items: list[dict] = []

    # Events referencing this contact
    events_q = await db.execute(
        select(Event)
        .where(
            Event.organization_id == organization_id,
            Event.entity_type == "contact",
            Event.entity_id == contact_id,
        )
        .order_by(Event.created_at.desc())
        .limit(limit)
    )
    for e in events_q.scalars():
        items.append({
            "type": "event",
            "event_type": e.event_type,
            "timestamp": e.created_at.isoformat() if isinstance(e.created_at, datetime) else str(e.created_at),
            "detail": e.payload_json or {},
        })

    # Deals linked to this contact
    deals_q = await db.execute(
        select(Deal)
        .where(Deal.organization_id == organization_id, Deal.contact_id == contact_id)
        .order_by(Deal.updated_at.desc())
        .limit(limit)
    )
    for d in deals_q.scalars():
        items.append({
            "type": "deal",
            "event_type": f"deal_{d.stage}",
            "timestamp": d.updated_at.isoformat() if isinstance(d.updated_at, datetime) else str(d.updated_at),
            "detail": {"deal_id": d.id, "title": d.title, "stage": d.stage, "value": float(d.value)},
        })

    # Notes mentioning this contact (by entity link)
    notes_q = await db.execute(
        select(Note)
        .where(
            Note.organization_id == organization_id,
            or_(
                Note.title.ilike(f"%contact:{contact_id}%"),
                Note.content.ilike(f"%contact:{contact_id}%"),
            ),
        )
        .order_by(Note.created_at.desc())
        .limit(20)
    )
    for n in notes_q.scalars():
        items.append({
            "type": "note",
            "event_type": "note_created",
            "timestamp": n.created_at.isoformat() if isinstance(n.created_at, datetime) else str(n.created_at),
            "detail": {"note_id": n.id, "title": n.title or (n.content[:60] if n.content else "")},
        })

    # Sort all items by timestamp descending
    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]
