"""Deal revenue split endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import deal_split as svc

router = APIRouter(prefix="/deal-splits", tags=["deal-splits"])


class SplitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    deal_id: int
    user_id: int
    split_pct: float
    split_amount: float
    role: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class SplitCreate(BaseModel):
    deal_id: int
    user_id: int
    split_pct: float = 100.0
    split_amount: float = 0.0
    role: str = "primary"
    notes: str | None = None


class SplitUpdate(BaseModel):
    split_pct: float | None = None
    split_amount: float | None = None
    role: str | None = None
    notes: str | None = None


@router.post("", response_model=SplitOut, status_code=201)
async def create_split(
    body: SplitCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_split(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("/deal/{deal_id}", response_model=list[SplitOut])
async def list_splits(
    deal_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_splits(db, actor["org_id"], deal_id)


@router.get("/deal/{deal_id}/summary")
async def get_summary(
    deal_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_summary(db, actor["org_id"], deal_id)


@router.put("/{split_id}", response_model=SplitOut)
async def update_split(
    split_id: int, body: SplitUpdate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    row = await svc.update_split(db, split_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Split not found")
    return row


@router.delete("/{split_id}", status_code=204)
async def delete_split(
    split_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_split(db, split_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Split not found")
