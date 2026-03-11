"""Win/loss analysis service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.win_loss_analysis import WinLossRecord


async def record_outcome(db: AsyncSession, *, organization_id: int, **kw) -> WinLossRecord:
    row = WinLossRecord(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_record(db: AsyncSession, record_id: int, org_id: int) -> WinLossRecord | None:
    return (await db.execute(select(WinLossRecord).where(WinLossRecord.id == record_id, WinLossRecord.organization_id == org_id))).scalar_one_or_none()


async def list_records(db: AsyncSession, org_id: int, *, outcome: str | None = None, limit: int = 50) -> list[WinLossRecord]:
    q = select(WinLossRecord).where(WinLossRecord.organization_id == org_id)
    if outcome:
        q = q.where(WinLossRecord.outcome == outcome)
    q = q.order_by(WinLossRecord.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_analytics(db: AsyncSession, org_id: int) -> dict:
    q = select(
        WinLossRecord.outcome,
        func.count(WinLossRecord.id).label("cnt"),
        func.sum(WinLossRecord.deal_amount).label("total_amount"),
        func.avg(WinLossRecord.sales_cycle_days).label("avg_cycle"),
    ).where(WinLossRecord.organization_id == org_id).group_by(WinLossRecord.outcome)
    rows = (await db.execute(q)).all()
    result = {}
    for r in rows:
        result[r.outcome] = {
            "count": r.cnt,
            "total_amount": round(float(r.total_amount or 0), 2),
            "avg_cycle_days": round(float(r.avg_cycle or 0), 1),
        }
    won = result.get("won", {}).get("count", 0)
    lost = result.get("lost", {}).get("count", 0)
    total = won + lost
    result["win_rate"] = round(won / max(total, 1) * 100, 1)
    return result


async def get_top_reasons(db: AsyncSession, org_id: int, outcome: str, limit: int = 10) -> list[dict]:
    q = (
        select(WinLossRecord.primary_reason, func.count(WinLossRecord.id).label("cnt"))
        .where(WinLossRecord.organization_id == org_id, WinLossRecord.outcome == outcome)
        .group_by(WinLossRecord.primary_reason)
        .order_by(func.count(WinLossRecord.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    return [{"reason": r.primary_reason, "count": r.cnt} for r in rows]
