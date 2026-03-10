"""Quote / proposal service."""
from __future__ import annotations

import json

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quote import Quote, QuoteLineItem


def _recalc(subtotal: float, discount_percent: float, tax_percent: float) -> float:
    after_discount = subtotal * (1 - discount_percent / 100)
    return round(after_discount * (1 + tax_percent / 100), 2)


async def create_quote(
    db: AsyncSession, *, organization_id: int, title: str,
    deal_id: int | None = None, contact_id: int | None = None,
    status: str = "draft", discount_percent: float = 0,
    tax_percent: float = 0, currency: str = "USD",
    expiry_date=None, notes: str | None = None,
    created_by_user_id: int | None = None,
) -> Quote:
    row = Quote(
        organization_id=organization_id, title=title,
        deal_id=deal_id, contact_id=contact_id, status=status,
        subtotal=0, discount_percent=discount_percent,
        tax_percent=tax_percent, total=0, currency=currency,
        expiry_date=expiry_date, notes=notes,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_quotes(
    db: AsyncSession, organization_id: int, *,
    status: str | None = None,
) -> list[Quote]:
    q = select(Quote).where(Quote.organization_id == organization_id)
    if status:
        q = q.where(Quote.status == status)
    q = q.order_by(Quote.updated_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_quote(db: AsyncSession, quote_id: int, organization_id: int) -> Quote | None:
    q = select(Quote).where(Quote.id == quote_id, Quote.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_quote(db: AsyncSession, quote_id: int, organization_id: int, **kwargs) -> Quote | None:
    row = await get_quote(db, quote_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    row.total = _recalc(float(row.subtotal), float(row.discount_percent), float(row.tax_percent))
    await db.commit()
    await db.refresh(row)
    return row


async def delete_quote(db: AsyncSession, quote_id: int, organization_id: int) -> bool:
    row = await get_quote(db, quote_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def add_line_item(
    db: AsyncSession, *, organization_id: int, quote_id: int,
    description: str, quantity: int = 1, unit_price: float = 0,
    discount_percent: float = 0, product_id: int | None = None,
) -> QuoteLineItem:
    line_total = round(quantity * unit_price * (1 - discount_percent / 100), 2)
    item = QuoteLineItem(
        organization_id=organization_id, quote_id=quote_id,
        product_id=product_id, description=description,
        quantity=quantity, unit_price=unit_price,
        discount_percent=discount_percent, line_total=line_total,
    )
    db.add(item)
    # Update quote subtotal
    quote = await get_quote(db, quote_id, organization_id)
    if quote:
        quote.subtotal = float(quote.subtotal) + line_total
        quote.total = _recalc(float(quote.subtotal), float(quote.discount_percent), float(quote.tax_percent))
    await db.commit()
    await db.refresh(item)
    return item


async def list_line_items(db: AsyncSession, organization_id: int, quote_id: int) -> list[QuoteLineItem]:
    q = select(QuoteLineItem).where(
        QuoteLineItem.organization_id == organization_id,
        QuoteLineItem.quote_id == quote_id,
    ).order_by(QuoteLineItem.id)
    return list((await db.execute(q)).scalars().all())


async def delete_line_item(db: AsyncSession, item_id: int, organization_id: int) -> bool:
    q = select(QuoteLineItem).where(QuoteLineItem.id == item_id, QuoteLineItem.organization_id == organization_id)
    item = (await db.execute(q)).scalar_one_or_none()
    if not item:
        return False
    quote = await get_quote(db, item.quote_id, organization_id)
    if quote:
        quote.subtotal = float(quote.subtotal) - float(item.line_total)
        quote.total = _recalc(float(quote.subtotal), float(quote.discount_percent), float(quote.tax_percent))
    await db.delete(item)
    await db.commit()
    return True
