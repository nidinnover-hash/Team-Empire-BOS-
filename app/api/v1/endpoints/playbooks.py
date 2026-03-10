"""Sales playbook endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import sales_playbook as svc

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


class PlaybookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    deal_stage: str | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PlaybookCreate(BaseModel):
    name: str
    deal_stage: str | None = None
    description: str | None = None
    is_active: bool = True


class PlaybookUpdate(BaseModel):
    name: str | None = None
    deal_stage: str | None = None
    description: str | None = None
    is_active: bool | None = None


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    playbook_id: int
    step_order: int
    title: str
    content: str | None = None
    is_required: bool
    created_at: datetime


class StepCreate(BaseModel):
    title: str
    step_order: int = 0
    content: str | None = None
    is_required: bool = False


@router.post("", response_model=PlaybookOut, status_code=201)
async def create_playbook(
    body: PlaybookCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_playbook(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[PlaybookOut])
async def list_playbooks(
    deal_stage: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_playbooks(db, actor["org_id"], deal_stage=deal_stage, is_active=is_active)


@router.get("/{playbook_id}", response_model=PlaybookOut)
async def get_playbook(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_playbook(db, playbook_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Playbook not found")
    return row


@router.put("/{playbook_id}", response_model=PlaybookOut)
async def update_playbook(
    playbook_id: int,
    body: PlaybookUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_playbook(db, playbook_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Playbook not found")
    return row


@router.delete("/{playbook_id}", status_code=204)
async def delete_playbook(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_playbook(db, playbook_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Playbook not found")


@router.post("/{playbook_id}/steps", response_model=StepOut, status_code=201)
async def add_step(
    playbook_id: int,
    body: StepCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.add_step(db, organization_id=actor["org_id"], playbook_id=playbook_id, **body.model_dump())


@router.get("/{playbook_id}/steps", response_model=list[StepOut])
async def list_steps(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_steps(db, actor["org_id"], playbook_id)


@router.delete("/steps/{step_id}", status_code=204)
async def delete_step(
    step_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    ok = await svc.delete_step(db, step_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Step not found")
