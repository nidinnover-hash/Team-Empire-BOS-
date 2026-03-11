"""Email analytics service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_analytics import EmailEvent

EVENT_TYPES = ["sent", "delivered", "opened", "clicked", "replied", "bounced"]


async def record_event(
    db: AsyncSession, *, organization_id: int,
    event_type: str, email_id: int | None = None,
    contact_id: int | None = None, link_url: str | None = None,
    user_agent: str | None = None,
) -> EmailEvent:
    row = EmailEvent(
        organization_id=organization_id, event_type=event_type,
        email_id=email_id, contact_id=contact_id,
        link_url=link_url, user_agent=user_agent,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_events(
    db: AsyncSession, organization_id: int, *,
    email_id: int | None = None, contact_id: int | None = None,
    event_type: str | None = None, limit: int = 100,
) -> list[EmailEvent]:
    q = select(EmailEvent).where(EmailEvent.organization_id == organization_id)
    if email_id is not None:
        q = q.where(EmailEvent.email_id == email_id)
    if contact_id is not None:
        q = q.where(EmailEvent.contact_id == contact_id)
    if event_type:
        q = q.where(EmailEvent.event_type == event_type)
    q = q.order_by(EmailEvent.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_email_metrics(db: AsyncSession, organization_id: int, email_id: int) -> dict:
    rows = (await db.execute(
        select(EmailEvent.event_type, func.count(EmailEvent.id))
        .where(EmailEvent.organization_id == organization_id, EmailEvent.email_id == email_id)
        .group_by(EmailEvent.event_type)
    )).all()
    return {t: c for t, c in rows}


async def get_contact_engagement(db: AsyncSession, organization_id: int, contact_id: int) -> dict:
    rows = (await db.execute(
        select(EmailEvent.event_type, func.count(EmailEvent.id))
        .where(EmailEvent.organization_id == organization_id, EmailEvent.contact_id == contact_id)
        .group_by(EmailEvent.event_type)
    )).all()
    return {t: c for t, c in rows}


async def get_overview(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(EmailEvent.event_type, func.count(EmailEvent.id))
        .where(EmailEvent.organization_id == organization_id)
        .group_by(EmailEvent.event_type)
    )).all()
    return {t: c for t, c in rows}
