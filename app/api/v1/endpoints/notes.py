from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db
from app.schemas.note import NoteCreate, NoteRead
from app.services import note as note_service

router = APIRouter(prefix="/notes", tags=["Notes"])


@router.post("", response_model=NoteRead, status_code=201)
async def create_note(
    data: NoteCreate,
    db: AsyncSession = Depends(get_db),
) -> NoteRead:
    """Save a short memory snippet."""
    return await note_service.create_note(db, data)


@router.get("", response_model=list[NoteRead])
async def list_notes(
    db: AsyncSession = Depends(get_db),
) -> list[NoteRead]:
    """Return the 50 most recent notes, newest first."""
    return await note_service.list_notes(db)
