from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.schemas.note import NoteCreate, NoteUpdate


async def create_note(
    db: AsyncSession, data: NoteCreate, organization_id: int
) -> Note:
    note = Note(**data.model_dump(), organization_id=organization_id)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def list_notes(
    db: AsyncSession, organization_id: int, limit: int = 50, offset: int = 0
) -> list[Note]:
    result = await db.execute(
        select(Note)
        .where(Note.organization_id == organization_id)
        .order_by(Note.created_at.desc(), Note.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_note(
    db: AsyncSession, note_id: int, organization_id: int,
) -> Note | None:
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def update_note(
    db: AsyncSession, note_id: int, data: NoteUpdate, organization_id: int,
) -> Note | None:
    note = await get_note(db, note_id, organization_id)
    if note is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(
    db: AsyncSession, note_id: int, organization_id: int,
) -> bool:
    note = await get_note(db, note_id, organization_id)
    if note is None:
        return False
    await db.delete(note)
    await db.commit()
    return True
