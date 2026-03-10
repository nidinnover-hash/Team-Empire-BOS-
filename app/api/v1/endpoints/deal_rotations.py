"""Deal rotation / round-robin endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import deal_rotation as svc

router = APIRouter(prefix="/deal-rotations", tags=["deal-rotations"])


class QueueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    current_index: int
    total_assignments: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class QueueCreate(BaseModel):
    name: str
    user_ids: list[int] | None = None
    is_active: bool = True


class QueueUpdate(BaseModel):
    name: str | None = None
    user_ids: list[int] | None = None
    is_active: bool | None = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    queue_id: int
    deal_id: int
    assigned_user_id: int
    created_at: datetime


class AssignBody(BaseModel):
    deal_id: int


@router.post("", response_model=QueueOut, status_code=201)
async def create_queue(
    body: QueueCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_queue(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[QueueOut])
async def list_queues(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_queues(db, actor["org_id"], is_active=is_active)


@router.get("/{queue_id}", response_model=QueueOut)
async def get_queue(
    queue_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_queue(db, queue_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Queue not found")
    return row


@router.put("/{queue_id}", response_model=QueueOut)
async def update_queue(
    queue_id: int,
    body: QueueUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_queue(db, queue_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Queue not found")
    return row


@router.delete("/{queue_id}", status_code=204)
async def delete_queue(
    queue_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_queue(db, queue_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Queue not found")


@router.post("/{queue_id}/assign", response_model=AssignmentOut, status_code=201)
async def assign_next(
    queue_id: int,
    body: AssignBody,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.assign_next(db, organization_id=actor["org_id"], queue_id=queue_id, deal_id=body.deal_id)
    if not row:
        raise HTTPException(400, "Queue inactive or empty")
    return row


@router.get("/{queue_id}/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    queue_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_assignments(db, actor["org_id"], queue_id, limit=limit)


@router.get("/{queue_id}/fairness")
async def get_fairness(
    queue_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_fairness(db, actor["org_id"], queue_id)
