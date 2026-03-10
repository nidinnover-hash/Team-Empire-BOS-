"""Territory management endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import territory as svc

router = APIRouter(prefix="/territories", tags=["territories"])


class TerritoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    region: str | None = None
    industry: str | None = None
    description: str | None = None
    assigned_user_id: int | None = None
    contact_count: int
    deal_count: int
    created_at: datetime
    updated_at: datetime


class TerritoryCreate(BaseModel):
    name: str
    region: str | None = None
    industry: str | None = None
    description: str | None = None
    assigned_user_id: int | None = None


class TerritoryUpdate(BaseModel):
    name: str | None = None
    region: str | None = None
    industry: str | None = None
    description: str | None = None
    assigned_user_id: int | None = None


@router.post("", response_model=TerritoryOut, status_code=201)
async def create_territory(
    body: TerritoryCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_territory(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[TerritoryOut])
async def list_territories(
    region: str | None = None,
    assigned_user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_territories(db, actor["org_id"], region=region, assigned_user_id=assigned_user_id)


@router.get("/{territory_id}", response_model=TerritoryOut)
async def get_territory(
    territory_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_territory(db, territory_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Territory not found")
    return row


@router.put("/{territory_id}", response_model=TerritoryOut)
async def update_territory(
    territory_id: int,
    body: TerritoryUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_territory(db, territory_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Territory not found")
    return row


@router.delete("/{territory_id}", status_code=204)
async def delete_territory(
    territory_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_territory(db, territory_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Territory not found")
