"""Meeting notes endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_roles
from app.core.deps import get_db
from app.services import meeting_note as svc

router = APIRouter(prefix="/meeting-notes", tags=["meeting-notes"])


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; organization_id: int; title: str
    summary: str | None = None; full_notes: str | None = None
    action_items_json: str; attendees_json: str
    contact_id: int | None = None; deal_id: int | None = None
    meeting_date: datetime | None = None
    created_by_user_id: int | None = None; created_at: datetime


class NoteCreate(BaseModel):
    title: str; summary: str | None = None
    full_notes: str | None = None
    action_items: list[dict] | None = None
    attendees: list[str] | None = None
    contact_id: int | None = None; deal_id: int | None = None


class NoteUpdate(BaseModel):
    title: str | None = None; summary: str | None = None
    full_notes: str | None = None
    action_items: list[dict] | None = None
    attendees: list[str] | None = None


@router.post("", response_model=NoteOut, status_code=201)
async def create_note(
    data: NoteCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_note(
        db, organization_id=actor["org_id"],
        created_by_user_id=actor["id"], **data.model_dump(),
    )


@router.get("", response_model=list[NoteOut])
async def list_notes(
    contact_id: int | None = None, deal_id: int | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_notes(db, actor["org_id"], contact_id=contact_id, deal_id=deal_id)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.get_note(db, note_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Note not found")
    return row


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: int, data: NoteUpdate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.update_note(db, note_id, actor["org_id"], **data.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Note not found")
    return row


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.delete_note(db, note_id, actor["org_id"]):
        raise HTTPException(404, "Note not found")
