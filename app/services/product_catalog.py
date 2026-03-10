"""Product catalog service."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_catalog import Product


async def create_product(
    db: AsyncSession, *, organization_id: int, name: str,
    sku: str | None = None, description: str | None = None,
    category: str | None = None, unit_price: float = 0.0,
    currency: str = "USD", pricing_tiers: list[dict] | None = None,
) -> Product:
    row = Product(
        organization_id=organization_id, name=name, sku=sku,
        description=description, category=category,
        unit_price=unit_price, currency=currency,
        pricing_tiers_json=json.dumps(pricing_tiers or []),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_products(
    db: AsyncSession, organization_id: int, *,
    category: str | None = None, is_active: bool | None = None,
) -> list[Product]:
    q = select(Product).where(Product.organization_id == organization_id)
    if category:
        q = q.where(Product.category == category)
    if is_active is not None:
        q = q.where(Product.is_active == is_active)
    q = q.order_by(Product.name)
    return list((await db.execute(q)).scalars().all())


async def get_product(db: AsyncSession, product_id: int, organization_id: int) -> Product | None:
    q = select(Product).where(Product.id == product_id, Product.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_product(db: AsyncSession, product_id: int, organization_id: int, **kwargs) -> Product | None:
    row = await get_product(db, product_id, organization_id)
    if not row:
        return None
    if "pricing_tiers" in kwargs:
        kwargs["pricing_tiers_json"] = json.dumps(kwargs.pop("pricing_tiers") or [])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_product(db: AsyncSession, product_id: int, organization_id: int) -> bool:
    row = await get_product(db, product_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
