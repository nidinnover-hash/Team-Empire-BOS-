"""Deal revenue split service."""
from __future__ import annotations

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal_split import DealSplit

_PROTECTED_FIELDS = {"id", "organization_id", "created_at"}


async def create_split(db: AsyncSession, *, organization_id: int, **kw) -> DealSplit:
    row = DealSplit(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_splits(db: AsyncSession, org_id: int, deal_id: int) -> list[DealSplit]:
    q = select(DealSplit).where(DealSplit.organization_id == org_id, DealSplit.deal_id == deal_id).order_by(DealSplit.split_pct.desc())
    return list((await db.execute(q)).scalars().all())


async def update_split(db: AsyncSession, split_id: int, org_id: int, **kw) -> DealSplit | None:
    row = (await db.execute(select(DealSplit).where(DealSplit.id == split_id, DealSplit.organization_id == org_id))).scalar_one_or_none()
    if not row:
        return None
    for k, v in kw.items():
        if k not in _PROTECTED_FIELDS:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_split(db: AsyncSession, split_id: int, org_id: int) -> bool:
    result = await db.execute(delete(DealSplit).where(DealSplit.id == split_id, DealSplit.organization_id == org_id))
    await db.commit()
    return (result.rowcount or 0) > 0


async def get_summary(db: AsyncSession, org_id: int, deal_id: int) -> dict:
    splits = await list_splits(db, org_id, deal_id)
    total_pct = sum(s.split_pct for s in splits)
    total_amount = sum(s.split_amount for s in splits)
    return {
        "deal_id": deal_id,
        "split_count": len(splits),
        "total_pct": round(total_pct, 2),
        "total_amount": round(total_amount, 2),
        "is_valid": abs(total_pct - 100.0) < 0.01,
    }
