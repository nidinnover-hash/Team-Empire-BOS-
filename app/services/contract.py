"""Contract tracking service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract

STATUSES = ["draft", "sent", "signed", "expired", "cancelled"]


async def create_contract(
    db: AsyncSession, *, organization_id: int, title: str,
    deal_id: int | None = None, contact_id: int | None = None,
    value: int = 0, status: str = "draft", notes: str | None = None,
    created_by_user_id: int | None = None,
) -> Contract:
    row = Contract(
        organization_id=organization_id, title=title,
        deal_id=deal_id, contact_id=contact_id, value=value,
        status=status, notes=notes, created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_contracts(
    db: AsyncSession, organization_id: int, *,
    status: str | None = None, deal_id: int | None = None, limit: int = 50,
) -> list[Contract]:
    q = select(Contract).where(Contract.organization_id == organization_id)
    if status:
        q = q.where(Contract.status == status)
    if deal_id is not None:
        q = q.where(Contract.deal_id == deal_id)
    q = q.order_by(Contract.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_contract(db: AsyncSession, contract_id: int, organization_id: int) -> Contract | None:
    q = select(Contract).where(Contract.id == contract_id, Contract.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_contract(db: AsyncSession, contract_id: int, organization_id: int, **kwargs) -> Contract | None:
    row = await get_contract(db, contract_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_contract(db: AsyncSession, contract_id: int, organization_id: int) -> bool:
    row = await get_contract(db, contract_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def get_summary(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(Contract.status, func.count(Contract.id), func.coalesce(func.sum(Contract.value), 0))
        .where(Contract.organization_id == organization_id)
        .group_by(Contract.status)
    )).all()
    return {s: {"count": c, "total_value": int(v)} for s, c, v in rows}
