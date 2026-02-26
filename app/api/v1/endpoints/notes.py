from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.note import NoteCreate, NoteRead
from app.services import note as note_service

router = APIRouter(prefix="/notes", tags=["Notes"])


@router.post("", response_model=NoteRead, status_code=201)
async def create_note(
    data: NoteCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> NoteRead:
    """Save a short memory snippet."""
    return await note_service.create_note(db, data, organization_id=actor["org_id"])


@router.get("", response_model=list[NoteRead])
async def list_notes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[NoteRead]:
    """Return notes, newest first. Use limit/offset for pagination."""
    return await note_service.list_notes(db, limit=limit, offset=offset, organization_id=actor["org_id"])
