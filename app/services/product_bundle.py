"""Product bundling service."""
from __future__ import annotations

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_bundle import ProductBundle, BundleItem


async def create_bundle(db: AsyncSession, *, organization_id: int, **kw) -> ProductBundle:
    row = ProductBundle(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_bundle(db: AsyncSession, bundle_id: int, org_id: int) -> ProductBundle | None:
    return (await db.execute(select(ProductBundle).where(ProductBundle.id == bundle_id, ProductBundle.organization_id == org_id))).scalar_one_or_none()


async def list_bundles(db: AsyncSession, org_id: int, *, is_active: bool | None = None) -> list[ProductBundle]:
    q = select(ProductBundle).where(ProductBundle.organization_id == org_id)
    if is_active is not None:
        q = q.where(ProductBundle.is_active == is_active)
    q = q.order_by(ProductBundle.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def update_bundle(db: AsyncSession, bundle_id: int, org_id: int, **kw) -> ProductBundle | None:
    row = await get_bundle(db, bundle_id, org_id)
    if not row:
        return None
    for k, v in kw.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_bundle(db: AsyncSession, bundle_id: int, org_id: int) -> bool:
    result = await db.execute(delete(ProductBundle).where(ProductBundle.id == bundle_id, ProductBundle.organization_id == org_id))
    await db.commit()
    return (result.rowcount or 0) > 0


async def add_item(db: AsyncSession, bundle_id: int, org_id: int, **kw) -> BundleItem | None:
    bundle = await get_bundle(db, bundle_id, org_id)
    if not bundle:
        return None
    item = BundleItem(bundle_id=bundle_id, **kw)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def list_items(db: AsyncSession, bundle_id: int) -> list[BundleItem]:
    q = select(BundleItem).where(BundleItem.bundle_id == bundle_id)
    return list((await db.execute(q)).scalars().all())


async def get_pricing(db: AsyncSession, bundle_id: int, org_id: int) -> dict:
    bundle = await get_bundle(db, bundle_id, org_id)
    if not bundle:
        return {}
    items = await list_items(db, bundle_id)
    individual = sum(i.unit_price * i.quantity for i in items)
    savings = individual - bundle.bundle_price if individual > 0 else 0
    return {
        "bundle_id": bundle_id,
        "bundle_price": bundle.bundle_price,
        "individual_total": round(individual, 2),
        "savings": round(savings, 2),
        "discount_pct": round(savings / individual * 100, 1) if individual > 0 else 0,
        "item_count": len(items),
    }
