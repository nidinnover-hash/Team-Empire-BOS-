from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.schemas.event import EventCreate


async def log_event(db: AsyncSession, data: EventCreate) -> Event:
    event = Event(**data.model_dump())
    db.add(event)
    await db.flush()  # get the ID before signing
    await db.refresh(event)

    # Sign the event for audit chain integrity
    try:
        from app.core.audit_integrity import sign_event
        await sign_event(db, event)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Audit signing skipped", exc_info=True)

    await db.commit()
    await db.refresh(event)
    return event


async def list_events(
    db: AsyncSession,
    organization_id: int,
    limit: int = 100,
    actor_user_id: int | None = None,
    event_date: date | None = None,
) -> list[Event]:
    query: Select[tuple[Event]] = select(Event)
    query = query.where(Event.organization_id == organization_id)
    if actor_user_id is not None:
        query = query.where(Event.actor_user_id == actor_user_id)
    if event_date is not None:
        query = query.where(func.date(Event.created_at) == event_date)
    query = query.order_by(Event.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
