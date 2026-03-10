"""Contract tracking endpoints."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import contract as svc

router = APIRouter(prefix="/contracts", tags=["contracts"])


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    title: str
    deal_id: int | None = None
    contact_id: int | None = None
    status: str
    value: float
    start_date: date | None = None
    end_date: date | None = None
    renewal_date: date | None = None
    auto_renew: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ContractCreate(BaseModel):
    title: str
    deal_id: int | None = None
    contact_id: int | None = None
    status: str = "draft"
    value: float = 0.0
    start_date: date | None = None
    end_date: date | None = None
    renewal_date: date | None = None
    auto_renew: bool = False
    notes: str | None = None


class ContractUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    value: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    renewal_date: date | None = None
    auto_renew: bool | None = None
    notes: str | None = None


@router.post("", response_model=ContractOut, status_code=201)
async def create_contract(
    body: ContractCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_contract(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[ContractOut])
async def list_contracts(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_contracts(db, actor["org_id"], status=status)


@router.get("/summary")
async def get_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_summary(db, actor["org_id"])


@router.get("/{contract_id}", response_model=ContractOut)
async def get_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_contract(db, contract_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Contract not found")
    return row


@router.put("/{contract_id}", response_model=ContractOut)
async def update_contract(
    contract_id: int,
    body: ContractUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_contract(db, contract_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Contract not found")
    return row


@router.delete("/{contract_id}", status_code=204)
async def delete_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_contract(db, contract_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Contract not found")
