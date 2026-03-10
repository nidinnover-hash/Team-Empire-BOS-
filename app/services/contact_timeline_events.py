"""Contact timeline events service (dedicated event table)."""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_timeline import ContactTimelineEvent


async def add_event(db: AsyncSession, *, organization_id: int, **kw) -> ContactTimelineEvent:
    row = ContactTimelineEvent(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_events(db: AsyncSession, org_id: int, contact_id: int, *, event_type: str | None = None, limit: int = 50) -> list[ContactTimelineEvent]:
    q = select(ContactTimelineEvent).where(
        ContactTimelineEvent.organization_id == org_id,
        ContactTimelineEvent.contact_id == contact_id,
    )
    if event_type:
        q = q.where(ContactTimelineEvent.event_type == event_type)
    q = q.order_by(ContactTimelineEvent.occurred_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_activity_summary(db: AsyncSession, org_id: int, contact_id: int) -> dict:
    q = (
        select(ContactTimelineEvent.event_type, func.count(ContactTimelineEvent.id).label("cnt"))
        .where(ContactTimelineEvent.organization_id == org_id, ContactTimelineEvent.contact_id == contact_id)
        .group_by(ContactTimelineEvent.event_type)
    )
    rows = (await db.execute(q)).all()
    breakdown = {r.event_type: r.cnt for r in rows}
    return {
        "contact_id": contact_id,
        "total_events": sum(breakdown.values()),
        "breakdown": breakdown,
    }
