"""Pipeline stage gate endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import stage_gate as svc

router = APIRouter(prefix="/stage-gates", tags=["stage-gates"])


class GateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    stage: str
    requirement_type: str
    field_name: str | None = None
    description: str
    is_blocking: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GateCreate(BaseModel):
    stage: str
    requirement_type: str = "field"
    field_name: str | None = None
    description: str = ""
    is_blocking: bool = True
    is_active: bool = True


class GateUpdate(BaseModel):
    stage: str | None = None
    requirement_type: str | None = None
    field_name: str | None = None
    description: str | None = None
    is_blocking: bool | None = None
    is_active: bool | None = None


class OverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    gate_id: int
    deal_id: int
    overridden_by_user_id: int
    reason: str | None = None
    created_at: datetime


class OverrideCreate(BaseModel):
    gate_id: int
    deal_id: int
    reason: str | None = None


class ValidateBody(BaseModel):
    stage: str
    deal_data: dict


@router.post("", response_model=GateOut, status_code=201)
async def create_gate(
    body: GateCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.create_gate(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[GateOut])
async def list_gates(
    stage: str | None = None, is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_gates(db, actor["org_id"], stage=stage, is_active=is_active)


@router.get("/{gate_id}", response_model=GateOut)
async def get_gate(
    gate_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_gate(db, gate_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Gate not found")
    return row


@router.put("/{gate_id}", response_model=GateOut)
async def update_gate(
    gate_id: int, body: GateUpdate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    row = await svc.update_gate(db, gate_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Gate not found")
    return row


@router.delete("/{gate_id}", status_code=204)
async def delete_gate(
    gate_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_gate(db, gate_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Gate not found")


@router.post("/overrides", response_model=OverrideOut, status_code=201)
async def record_override(
    body: OverrideCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.record_override(db, organization_id=actor["org_id"], overridden_by_user_id=actor["id"], **body.model_dump())


@router.get("/overrides/list", response_model=list[OverrideOut])
async def list_overrides(
    deal_id: int | None = None, gate_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_overrides(db, actor["org_id"], deal_id=deal_id, gate_id=gate_id)


@router.post("/validate")
async def validate_stage(
    body: ValidateBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.validate_stage(db, actor["org_id"], body.stage, body.deal_data)
