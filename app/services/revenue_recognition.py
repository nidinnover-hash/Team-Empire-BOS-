"""Revenue recognition service."""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revenue_recognition import RevenueEntry

STAGES = ["contract", "delivery", "acceptance", "billing", "complete"]


async def create_entry(
    db: AsyncSession, *, organization_id: int, period: str,
    total_amount: float, recognized_amount: float = 0.0,
    deferred_amount: float = 0.0, recognition_stage: str = "contract",
    deal_id: int | None = None, notes: str | None = None,
) -> RevenueEntry:
    row = RevenueEntry(
        organization_id=organization_id, period=period,
        total_amount=total_amount, recognized_amount=recognized_amount,
        deferred_amount=deferred_amount, recognition_stage=recognition_stage,
        deal_id=deal_id, notes=notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_entries(
    db: AsyncSession, organization_id: int, *,
    period: str | None = None, deal_id: int | None = None, limit: int = 50,
) -> list[RevenueEntry]:
    q = select(RevenueEntry).where(RevenueEntry.organization_id == organization_id)
    if period:
        q = q.where(RevenueEntry.period == period)
    if deal_id is not None:
        q = q.where(RevenueEntry.deal_id == deal_id)
    q = q.order_by(RevenueEntry.period.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_entry(db: AsyncSession, entry_id: int, organization_id: int) -> RevenueEntry | None:
    q = select(RevenueEntry).where(RevenueEntry.id == entry_id, RevenueEntry.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_entry(db: AsyncSession, entry_id: int, organization_id: int, **kwargs) -> RevenueEntry | None:
    row = await get_entry(db, entry_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def get_period_summary(db: AsyncSession, organization_id: int, period: str) -> dict:
    q = (
        select(
            func.coalesce(func.sum(RevenueEntry.total_amount), 0),
            func.coalesce(func.sum(RevenueEntry.recognized_amount), 0),
            func.coalesce(func.sum(RevenueEntry.deferred_amount), 0),
            func.count(RevenueEntry.id),
        )
        .where(RevenueEntry.organization_id == organization_id, RevenueEntry.period == period)
    )
    row = (await db.execute(q)).one()
    return {
        "period": period,
        "total_amount": float(row[0]),
        "recognized_amount": float(row[1]),
        "deferred_amount": float(row[2]),
        "entry_count": row[3],
    }
