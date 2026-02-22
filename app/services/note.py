from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.note import Note
from app.schemas.note import NoteCreate


async def create_note(
    db: AsyncSession, data: NoteCreate, organization_id: int = 1
) -> Note:
    note = Note(**data.model_dump(), organization_id=organization_id)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def list_notes(
    db: AsyncSession, limit: int = 50, offset: int = 0, organization_id: int = 1
) -> list[Note]:
    result = await db.execute(
        select(Note)
        .where(Note.organization_id == organization_id)
        .order_by(Note.created_at.desc(), Note.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())
