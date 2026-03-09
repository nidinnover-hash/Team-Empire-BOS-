"""Commission calculator service."""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commission import CommissionRule, CommissionPayout


async def create_rule(
    db: AsyncSession, *, organization_id: int, name: str,
    rate_percent: float = 10.0, deal_type: str | None = None,
    stage: str | None = None, min_deal_value: int = 0,
    max_deal_value: int | None = None,
) -> CommissionRule:
    row = CommissionRule(
        organization_id=organization_id, name=name,
        rate_percent=rate_percent, deal_type=deal_type, stage=stage,
        min_deal_value=min_deal_value, max_deal_value=max_deal_value,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_rules(db: AsyncSession, organization_id: int, *, is_active: bool | None = None) -> list[CommissionRule]:
    q = select(CommissionRule).where(CommissionRule.organization_id == organization_id)
    if is_active is not None:
        q = q.where(CommissionRule.is_active == is_active)
    q = q.order_by(CommissionRule.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def update_rule(db: AsyncSession, rule_id: int, organization_id: int, **kwargs) -> CommissionRule | None:
    q = select(CommissionRule).where(CommissionRule.id == rule_id, CommissionRule.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_rule(db: AsyncSession, rule_id: int, organization_id: int) -> bool:
    q = select(CommissionRule).where(CommissionRule.id == rule_id, CommissionRule.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def calculate_payout(
    db: AsyncSession, *, organization_id: int, rule_id: int,
    deal_id: int, user_id: int, deal_value: int, split_percent: float = 100.0,
    notes: str | None = None,
) -> CommissionPayout:
    q = select(CommissionRule).where(CommissionRule.id == rule_id, CommissionRule.organization_id == organization_id)
    rule = (await db.execute(q)).scalar_one_or_none()
    rate = rule.rate_percent if rule else 10.0
    commission_amount = deal_value * (rate / 100) * (split_percent / 100)
    payout = CommissionPayout(
        organization_id=organization_id, rule_id=rule_id,
        deal_id=deal_id, user_id=user_id, deal_value=deal_value,
        commission_amount=commission_amount, split_percent=split_percent,
        notes=notes,
    )
    db.add(payout)
    await db.commit()
    await db.refresh(payout)
    return payout


async def list_payouts(
    db: AsyncSession, organization_id: int, *,
    user_id: int | None = None, status: str | None = None, limit: int = 50,
) -> list[CommissionPayout]:
    q = select(CommissionPayout).where(CommissionPayout.organization_id == organization_id)
    if user_id is not None:
        q = q.where(CommissionPayout.user_id == user_id)
    if status:
        q = q.where(CommissionPayout.status == status)
    q = q.order_by(CommissionPayout.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def update_payout_status(db: AsyncSession, payout_id: int, organization_id: int, status: str) -> CommissionPayout | None:
    q = select(CommissionPayout).where(CommissionPayout.id == payout_id, CommissionPayout.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return None
    row.status = status
    await db.commit()
    await db.refresh(row)
    return row


async def get_summary(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(CommissionPayout.status, func.count(CommissionPayout.id), func.coalesce(func.sum(CommissionPayout.commission_amount), 0))
        .where(CommissionPayout.organization_id == organization_id)
        .group_by(CommissionPayout.status)
    )).all()
    summary = {}
    for status, count, total in rows:
        summary[status] = {"count": count, "total": float(total)}
    return summary
