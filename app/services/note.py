from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.note import Note
from app.schemas.note import NoteCreate


async def create_note(db: AsyncSession, data: NoteCreate) -> Note:
    note = Note(**data.model_dump())
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def list_notes(db: AsyncSession, limit: int = 50) -> list[Note]:
    result = await db.execute(
        select(Note).order_by(Note.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
