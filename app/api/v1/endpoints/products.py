"""Product catalog endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import product_catalog as svc

router = APIRouter(prefix="/products", tags=["products"])


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    unit_price: float
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    name: str
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    unit_price: float = 0.0
    currency: str = "USD"
    pricing_tiers: list[dict] | None = None
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    unit_price: float | None = None
    currency: str | None = None
    pricing_tiers: list[dict] | None = None
    is_active: bool | None = None


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.create_product(db, organization_id=actor["org_id"], **body.model_dump())
    return row


@router.get("", response_model=list[ProductOut])
async def list_products(
    category: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_products(db, actor["org_id"], category=category, is_active=is_active)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_product(db, product_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Product not found")
    return row


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_product(db, product_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Product not found")
    return row


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_product(db, product_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Product not found")
