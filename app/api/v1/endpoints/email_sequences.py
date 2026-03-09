"""Email sequence automation endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_roles
from app.core.deps import get_db
from app.services import email_sequence as svc

router = APIRouter(prefix="/email-sequences", tags=["email-sequences"])


class SequenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    description: str | None = None
    trigger_event: str
    exit_condition: str | None = None
    is_active: bool
    total_enrolled: int
    total_completed: int
    created_by_user_id: int | None = None
    created_at: datetime


class SequenceCreate(BaseModel):
    name: str
    trigger_event: str
    description: str | None = None
    exit_condition: str | None = None


class SequenceUpdate(BaseModel):
    name: str | None = None
    trigger_event: str | None = None
    description: str | None = None
    exit_condition: str | None = None
    is_active: bool | None = None


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sequence_id: int
    step_order: int
    delay_hours: int
    subject: str
    body: str
    template_id: int | None = None
    created_at: datetime


class StepCreate(BaseModel):
    step_order: int = 1
    delay_hours: int = 24
    subject: str
    body: str
    template_id: int | None = None


@router.post("", response_model=SequenceOut, status_code=201)
async def create_sequence(
    data: SequenceCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_sequence(
        db, organization_id=actor["org_id"],
        created_by_user_id=actor["id"], **data.model_dump(),
    )


@router.get("", response_model=list[SequenceOut])
async def list_sequences(
    is_active: bool | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_sequences(db, actor["org_id"], is_active=is_active)


@router.get("/stats")
async def get_stats(
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_stats(db, actor["org_id"])


@router.get("/{sequence_id}", response_model=SequenceOut)
async def get_sequence(
    sequence_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    seq = await svc.get_sequence(db, sequence_id, actor["org_id"])
    if not seq:
        raise HTTPException(404, "Sequence not found")
    return seq


@router.patch("/{sequence_id}", response_model=SequenceOut)
async def update_sequence(
    sequence_id: int,
    data: SequenceUpdate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    seq = await svc.update_sequence(
        db, sequence_id, actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if not seq:
        raise HTTPException(404, "Sequence not found")
    return seq


@router.delete("/{sequence_id}", status_code=204)
async def delete_sequence(
    sequence_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.delete_sequence(db, sequence_id, actor["org_id"]):
        raise HTTPException(404, "Sequence not found")


@router.post("/{sequence_id}/steps", response_model=StepOut, status_code=201)
async def add_step(
    sequence_id: int,
    data: StepCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    seq = await svc.get_sequence(db, sequence_id, actor["org_id"])
    if not seq:
        raise HTTPException(404, "Sequence not found")
    return await svc.add_step(db, sequence_id=sequence_id, **data.model_dump())


@router.get("/{sequence_id}/steps", response_model=list[StepOut])
async def list_steps(
    sequence_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_steps(db, sequence_id)


@router.delete("/{sequence_id}/steps/{step_id}", status_code=204)
async def delete_step(
    sequence_id: int,
    step_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.delete_step(db, step_id):
        raise HTTPException(404, "Step not found")
