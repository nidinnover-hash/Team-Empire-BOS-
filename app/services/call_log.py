"""Call logging service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_log import CallLog


async def create_call(db: AsyncSession, *, organization_id: int, **kw) -> CallLog:
    row = CallLog(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_call(db: AsyncSession, call_id: int, org_id: int) -> CallLog | None:
    return (await db.execute(select(CallLog).where(CallLog.id == call_id, CallLog.organization_id == org_id))).scalar_one_or_none()


async def list_calls(db: AsyncSession, org_id: int, *, contact_id: int | None = None, deal_id: int | None = None, user_id: int | None = None, limit: int = 50) -> list[CallLog]:
    q = select(CallLog).where(CallLog.organization_id == org_id)
    if contact_id:
        q = q.where(CallLog.contact_id == contact_id)
    if deal_id:
        q = q.where(CallLog.deal_id == deal_id)
    if user_id:
        q = q.where(CallLog.user_id == user_id)
    q = q.order_by(CallLog.called_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_stats(db: AsyncSession, org_id: int, user_id: int | None = None) -> dict:
    q = select(
        func.count(CallLog.id).label("total_calls"),
        func.sum(CallLog.duration_seconds).label("total_duration"),
        func.avg(CallLog.duration_seconds).label("avg_duration"),
    ).where(CallLog.organization_id == org_id)
    if user_id:
        q = q.where(CallLog.user_id == user_id)
    row = (await db.execute(q)).one()
    return {
        "total_calls": row.total_calls or 0,
        "total_duration": row.total_duration or 0,
        "avg_duration": round(float(row.avg_duration or 0), 1),
    }
