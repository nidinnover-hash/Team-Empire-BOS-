"""Deal dependency endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import deal_dependency as svc

router = APIRouter(prefix="/deal-dependencies", tags=["deal-dependencies"])


class DepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    deal_id: int
    depends_on_deal_id: int
    dependency_type: str
    is_resolved: bool
    notes: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class DepCreate(BaseModel):
    deal_id: int
    depends_on_deal_id: int
    dependency_type: str = "blocks"
    notes: str | None = None


@router.post("", response_model=DepOut, status_code=201)
async def create_dependency(
    body: DepCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_dependency(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("/deal/{deal_id}", response_model=list[DepOut])
async def list_dependencies(
    deal_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_dependencies(db, actor["org_id"], deal_id)


@router.get("/deal/{deal_id}/blockers", response_model=list[DepOut])
async def get_blockers(
    deal_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_blockers(db, actor["org_id"], deal_id)


@router.put("/{dep_id}/resolve", response_model=DepOut)
async def resolve_dependency(
    dep_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.resolve_dependency(db, dep_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Dependency not found")
    return row


@router.delete("/{dep_id}", status_code=204)
async def delete_dependency(
    dep_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_dependency(db, dep_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Dependency not found")
