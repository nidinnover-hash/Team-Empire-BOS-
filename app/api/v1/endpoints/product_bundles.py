"""Product bundling endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import product_bundle as svc

router = APIRouter(prefix="/product-bundles", tags=["product-bundles"])


class BundleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    description: str | None = None
    bundle_price: float
    individual_total: float
    discount_pct: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BundleCreate(BaseModel):
    name: str
    description: str | None = None
    bundle_price: float = 0.0
    individual_total: float = 0.0
    discount_pct: float = 0.0
    is_active: bool = True


class BundleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    bundle_price: float | None = None
    individual_total: float | None = None
    discount_pct: float | None = None
    is_active: bool | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    bundle_id: int
    product_id: int
    quantity: int
    unit_price: float


class ItemCreate(BaseModel):
    product_id: int
    quantity: int = 1
    unit_price: float = 0.0


@router.post("", response_model=BundleOut, status_code=201)
async def create_bundle(
    body: BundleCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.create_bundle(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[BundleOut])
async def list_bundles(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_bundles(db, actor["org_id"], is_active=is_active)


@router.get("/{bundle_id}", response_model=BundleOut)
async def get_bundle(
    bundle_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_bundle(db, bundle_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Bundle not found")
    return row


@router.put("/{bundle_id}", response_model=BundleOut)
async def update_bundle(
    bundle_id: int, body: BundleUpdate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    row = await svc.update_bundle(db, bundle_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Bundle not found")
    return row


@router.delete("/{bundle_id}", status_code=204)
async def delete_bundle(
    bundle_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_bundle(db, bundle_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Bundle not found")


@router.post("/{bundle_id}/items", response_model=ItemOut, status_code=201)
async def add_item(
    bundle_id: int, body: ItemCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    item = await svc.add_item(db, bundle_id, actor["org_id"], **body.model_dump())
    if not item:
        raise HTTPException(404, "Bundle not found")
    return item


@router.get("/{bundle_id}/items", response_model=list[ItemOut])
async def list_items(
    bundle_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_items(db, bundle_id, actor["org_id"])


@router.get("/{bundle_id}/pricing")
async def get_pricing(
    bundle_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_pricing(db, bundle_id, actor["org_id"])
