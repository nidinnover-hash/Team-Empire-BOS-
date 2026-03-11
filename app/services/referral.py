"""Referral program service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral import Referral, ReferralSource


async def create_source(
    db: AsyncSession, *, organization_id: int, name: str,
    tracking_code: str, reward_type: str = "flat",
    reward_value: float = 0.0, notes: str | None = None,
) -> ReferralSource:
    row = ReferralSource(
        organization_id=organization_id, name=name,
        tracking_code=tracking_code, reward_type=reward_type,
        reward_value=reward_value, notes=notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_sources(db: AsyncSession, organization_id: int) -> list[ReferralSource]:
    q = select(ReferralSource).where(ReferralSource.organization_id == organization_id).order_by(ReferralSource.name)
    return list((await db.execute(q)).scalars().all())


async def get_source(db: AsyncSession, source_id: int, organization_id: int) -> ReferralSource | None:
    q = select(ReferralSource).where(ReferralSource.id == source_id, ReferralSource.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def create_referral(
    db: AsyncSession, *, organization_id: int, source_id: int,
    contact_id: int | None = None, deal_id: int | None = None,
) -> Referral:
    row = Referral(
        organization_id=organization_id, source_id=source_id,
        contact_id=contact_id, deal_id=deal_id,
    )
    db.add(row)
    # Increment referral count
    src = await get_source(db, source_id, organization_id)
    if src:
        src.total_referrals += 1
    await db.commit()
    await db.refresh(row)
    return row


async def list_referrals(
    db: AsyncSession, organization_id: int, *,
    source_id: int | None = None, status: str | None = None, limit: int = 50,
) -> list[Referral]:
    q = select(Referral).where(Referral.organization_id == organization_id)
    if source_id is not None:
        q = q.where(Referral.source_id == source_id)
    if status:
        q = q.where(Referral.status == status)
    q = q.order_by(Referral.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def convert_referral(db: AsyncSession, referral_id: int, organization_id: int, reward_amount: float = 0.0) -> Referral | None:
    q = select(Referral).where(Referral.id == referral_id, Referral.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return None
    row.status = "converted"
    row.reward_amount = reward_amount
    src = await get_source(db, row.source_id, organization_id)
    if src:
        src.total_conversions += 1
        src.total_rewards_paid += reward_amount
    await db.commit()
    await db.refresh(row)
    return row


async def get_stats(db: AsyncSession, organization_id: int) -> dict:
    total = (await db.execute(
        select(func.count(Referral.id)).where(Referral.organization_id == organization_id)
    )).scalar() or 0
    converted = (await db.execute(
        select(func.count(Referral.id)).where(Referral.organization_id == organization_id, Referral.status == "converted")
    )).scalar() or 0
    rewards = (await db.execute(
        select(func.coalesce(func.sum(Referral.reward_amount), 0)).where(Referral.organization_id == organization_id)
    )).scalar() or 0
    return {"total_referrals": total, "total_conversions": converted, "total_rewards": float(rewards), "conversion_rate": round(converted / total * 100, 1) if total > 0 else 0}
