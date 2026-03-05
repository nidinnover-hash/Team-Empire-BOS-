from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_workspace_id, get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.note import NoteCreate, NoteRead, NoteUpdate
from app.services import note as note_service

router = APIRouter(prefix="/notes", tags=["Notes"])


@router.post("", response_model=NoteRead, status_code=201)
async def create_note(
    data: NoteCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> NoteRead:
    """Save a short memory snippet."""
    note = await note_service.create_note(db, data, organization_id=actor["org_id"])
    await record_action(
        db, event_type="note_created", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="note", entity_id=note.id,
    )
    return note


@router.get("", response_model=list[NoteRead])
async def list_notes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> list[NoteRead]:
    """Return notes, newest first. Use limit/offset for pagination."""
    return await note_service.list_notes(db, limit=limit, offset=offset, organization_id=actor["org_id"])


@router.get("/{note_id}", response_model=NoteRead)
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> NoteRead:
    note = await note_service.get_note(db, note_id, organization_id=actor["org_id"])
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: int,
    data: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> NoteRead:
    note = await note_service.update_note(db, note_id, data, organization_id=actor["org_id"])
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    await record_action(
        db, event_type="note_updated", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="note", entity_id=note_id,
        payload_json=data.model_dump(exclude_unset=True),
    )
    return note


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> None:
    deleted = await note_service.delete_note(db, note_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    await record_action(
        db, event_type="note_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="note", entity_id=note_id,
    )
