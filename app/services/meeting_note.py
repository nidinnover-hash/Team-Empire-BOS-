"""Meeting notes service."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meeting_note import MeetingNote


async def create_note(
    db: AsyncSession, *, organization_id: int, title: str,
    summary: str | None = None, full_notes: str | None = None,
    action_items: list[dict] | None = None, attendees: list[str] | None = None,
    contact_id: int | None = None, deal_id: int | None = None,
    meeting_date: str | None = None, created_by_user_id: int | None = None,
) -> MeetingNote:
    row = MeetingNote(
        organization_id=organization_id, title=title,
        summary=summary, full_notes=full_notes,
        action_items_json=json.dumps(action_items or []),
        attendees_json=json.dumps(attendees or []),
        contact_id=contact_id, deal_id=deal_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_notes(
    db: AsyncSession, organization_id: int, *,
    contact_id: int | None = None, deal_id: int | None = None, limit: int = 50,
) -> list[MeetingNote]:
    q = select(MeetingNote).where(MeetingNote.organization_id == organization_id)
    if contact_id is not None:
        q = q.where(MeetingNote.contact_id == contact_id)
    if deal_id is not None:
        q = q.where(MeetingNote.deal_id == deal_id)
    q = q.order_by(MeetingNote.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_note(db: AsyncSession, note_id: int, organization_id: int) -> MeetingNote | None:
    q = select(MeetingNote).where(MeetingNote.id == note_id, MeetingNote.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_note(db: AsyncSession, note_id: int, organization_id: int, **kwargs) -> MeetingNote | None:
    row = await get_note(db, note_id, organization_id)
    if not row:
        return None
    if "action_items" in kwargs:
        kwargs["action_items_json"] = json.dumps(kwargs.pop("action_items") or [])
    if "attendees" in kwargs:
        kwargs["attendees_json"] = json.dumps(kwargs.pop("attendees") or [])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_note(db: AsyncSession, note_id: int, organization_id: int) -> bool:
    row = await get_note(db, note_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
