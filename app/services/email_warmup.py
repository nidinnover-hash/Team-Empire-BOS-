"""Email warmup tracking service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_warmup import EmailWarmup


async def create_warmup(db: AsyncSession, *, organization_id: int, **kw) -> EmailWarmup:
    row = EmailWarmup(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_warmup(db: AsyncSession, warmup_id: int, org_id: int) -> EmailWarmup | None:
    return (await db.execute(select(EmailWarmup).where(EmailWarmup.id == warmup_id, EmailWarmup.organization_id == org_id))).scalar_one_or_none()


async def list_warmups(db: AsyncSession, org_id: int, *, is_active: bool | None = None) -> list[EmailWarmup]:
    q = select(EmailWarmup).where(EmailWarmup.organization_id == org_id)
    if is_active is not None:
        q = q.where(EmailWarmup.is_active == is_active)
    q = q.order_by(EmailWarmup.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def advance_day(db: AsyncSession, warmup_id: int, org_id: int) -> EmailWarmup | None:
    row = await get_warmup(db, warmup_id, org_id)
    if not row:
        return None
    row.warmup_day += 1
    row.daily_limit = min(row.daily_limit + row.ramp_increment, row.target_daily)
    row.current_daily = 0
    if row.daily_limit >= row.target_daily:
        row.is_active = False
        row.reputation_score = 100
    await db.commit()
    await db.refresh(row)
    return row


async def get_status(db: AsyncSession, org_id: int) -> dict:
    warmups = await list_warmups(db, org_id)
    active = [w for w in warmups if w.is_active]
    completed = [w for w in warmups if not w.is_active]
    return {
        "total": len(warmups),
        "active": len(active),
        "completed": len(completed),
        "avg_reputation": round(sum(w.reputation_score for w in warmups) / max(len(warmups), 1), 1),
    }
