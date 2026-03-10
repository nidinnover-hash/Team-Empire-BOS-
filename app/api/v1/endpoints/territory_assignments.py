"""Territory assignment endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import territory_assignment as svc

router = APIRouter(prefix="/territory-assignments", tags=["territory-assignments"])


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    territory_id: int
    user_id: int
    role: str
    quota: float
    current_revenue: float
    deal_count: int
    is_primary: bool
    assigned_at: datetime
    created_at: datetime


class AssignmentCreate(BaseModel):
    territory_id: int
    user_id: int
    role: str = "rep"
    quota: float = 0.0
    is_primary: bool = True


@router.post("", response_model=AssignmentOut, status_code=201)
async def create_assignment(
    body: AssignmentCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.create_assignment(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[AssignmentOut])
async def list_assignments(
    territory_id: int | None = None, user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_assignments(db, actor["org_id"], territory_id=territory_id, user_id=user_id)


@router.get("/coverage")
async def get_coverage(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_coverage(db, actor["org_id"])


@router.delete("/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_assignment(db, assignment_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Assignment not found")
