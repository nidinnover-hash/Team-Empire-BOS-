"""Recurring invoice service — CRUD and generation scheduling."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring_invoice import RecurringInvoice


async def create_recurring_invoice(
    db: AsyncSession, organization_id: int, created_by: int | None = None, **kwargs,
) -> RecurringInvoice:
    if "line_items" in kwargs:
        kwargs["line_items_json"] = json.dumps(kwargs.pop("line_items"))
    inv = RecurringInvoice(organization_id=organization_id, created_by_user_id=created_by, **kwargs)
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return inv


async def list_recurring_invoices(
    db: AsyncSession, organization_id: int, active_only: bool = True,
) -> list[RecurringInvoice]:
    q = select(RecurringInvoice).where(RecurringInvoice.organization_id == organization_id)
    if active_only:
        q = q.where(RecurringInvoice.is_active.is_(True))
    result = await db.execute(q.order_by(RecurringInvoice.id))
    return list(result.scalars().all())


async def get_recurring_invoice(
    db: AsyncSession, invoice_id: int, organization_id: int,
) -> RecurringInvoice | None:
    result = await db.execute(
        select(RecurringInvoice).where(
            RecurringInvoice.id == invoice_id,
            RecurringInvoice.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_recurring_invoice(
    db: AsyncSession, invoice_id: int, organization_id: int, **kwargs,
) -> RecurringInvoice | None:
    inv = await get_recurring_invoice(db, invoice_id, organization_id)
    if not inv:
        return None
    if "line_items" in kwargs:
        kwargs["line_items_json"] = json.dumps(kwargs.pop("line_items"))
    for k, v in kwargs.items():
        if v is not None and hasattr(inv, k):
            setattr(inv, k, v)
    await db.commit()
    await db.refresh(inv)
    return inv


async def delete_recurring_invoice(
    db: AsyncSession, invoice_id: int, organization_id: int,
) -> bool:
    inv = await get_recurring_invoice(db, invoice_id, organization_id)
    if not inv:
        return False
    inv.is_active = False
    await db.commit()
    return True


async def mark_generated(
    db: AsyncSession, invoice_id: int, organization_id: int,
) -> RecurringInvoice | None:
    """Mark invoice as generated (increment counter, update timestamp)."""
    inv = await get_recurring_invoice(db, invoice_id, organization_id)
    if not inv:
        return None
    inv.total_generated += 1
    inv.last_generated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(inv)
    return inv


async def get_due_invoices(
    db: AsyncSession, organization_id: int,
) -> list[RecurringInvoice]:
    """Get active recurring invoices that are due for generation."""
    now = datetime.now(UTC)
    q = select(RecurringInvoice).where(
        RecurringInvoice.organization_id == organization_id,
        RecurringInvoice.is_active.is_(True),
        RecurringInvoice.next_due_date <= now,
    )
    result = await db.execute(q.order_by(RecurringInvoice.next_due_date))
    return list(result.scalars().all())
