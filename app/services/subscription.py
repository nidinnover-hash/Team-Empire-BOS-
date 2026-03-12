"""Subscription management service."""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription, SubscriptionPlan


async def create_plan(
    db: AsyncSession, *, organization_id: int, name: str,
    billing_cycle: str = "monthly", price: float = 0,
    currency: str = "USD", features: list[str] | None = None,
    is_active: bool = True,
) -> SubscriptionPlan:
    row = SubscriptionPlan(
        organization_id=organization_id, name=name,
        billing_cycle=billing_cycle, price=price, currency=currency,
        features_json=json.dumps(features or []), is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_plans(db: AsyncSession, organization_id: int, *, is_active: bool | None = None) -> list[SubscriptionPlan]:
    q = select(SubscriptionPlan).where(SubscriptionPlan.organization_id == organization_id)
    if is_active is not None:
        q = q.where(SubscriptionPlan.is_active == is_active)
    q = q.order_by(SubscriptionPlan.price)
    return list((await db.execute(q)).scalars().all())


async def get_plan(db: AsyncSession, plan_id: int, organization_id: int) -> SubscriptionPlan | None:
    q = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id, SubscriptionPlan.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def create_subscription(
    db: AsyncSession, *, organization_id: int, plan_id: int,
    contact_id: int | None = None, start_date=None,
    end_date=None, next_billing_date=None, mrr: float = 0,
    status: str = "active",
) -> Subscription:
    row = Subscription(
        organization_id=organization_id, plan_id=plan_id,
        contact_id=contact_id, start_date=start_date,
        end_date=end_date, next_billing_date=next_billing_date,
        mrr=mrr, status=status,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_subscriptions(
    db: AsyncSession, organization_id: int, *,
    status: str | None = None, plan_id: int | None = None,
) -> list[Subscription]:
    q = select(Subscription).where(Subscription.organization_id == organization_id)
    if status:
        q = q.where(Subscription.status == status)
    if plan_id is not None:
        q = q.where(Subscription.plan_id == plan_id)
    q = q.order_by(Subscription.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_subscription(db: AsyncSession, sub_id: int, organization_id: int) -> Subscription | None:
    q = select(Subscription).where(Subscription.id == sub_id, Subscription.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_subscription(db: AsyncSession, sub_id: int, organization_id: int, **kwargs) -> Subscription | None:
    row = await get_subscription(db, sub_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def cancel_subscription(db: AsyncSession, sub_id: int, organization_id: int) -> Subscription | None:
    row = await get_subscription(db, sub_id, organization_id)
    if not row:
        return None
    row.status = "cancelled"
    await db.commit()
    await db.refresh(row)
    return row


async def get_mrr_summary(db: AsyncSession, organization_id: int) -> dict:
    total_mrr = (await db.execute(
        select(func.coalesce(func.sum(Subscription.mrr), 0))
        .where(Subscription.organization_id == organization_id, Subscription.status == "active")
    )).scalar() or 0
    active = (await db.execute(
        select(func.count(Subscription.id))
        .where(Subscription.organization_id == organization_id, Subscription.status == "active")
    )).scalar() or 0
    return {"total_mrr": float(total_mrr), "active_subscriptions": active}
