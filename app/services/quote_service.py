"""Quote and line item service — CRM module.

All business logic for quotes and line items. Organization-scoped; emits signals for audit.
"""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quote import Quote, QuoteLineItem
from app.platform.signals import (
    QUOTE_CREATED,
    QUOTE_LINE_ITEM_ADDED,
    QUOTE_LINE_ITEM_REMOVED,
    QUOTE_UPDATED,
    SignalCategory,
    SignalEnvelope,
    publish_signal,
)
from app.schemas.quote import QuoteCreate, QuoteLineItemCreate, QuoteLineItemUpdate, QuoteUpdate

logger = logging.getLogger(__name__)

_PROTECTED_QUOTE_FIELDS = frozenset({"id", "organization_id", "created_by_user_id", "created_at"})
_QUOTE_UPDATE_FIELDS = frozenset({
    "title", "deal_id", "contact_id", "status", "discount_percent", "tax_percent",
    "currency", "expiry_date", "notes",
})


def _line_total(quantity: int, unit_price: float | Decimal, discount_percent: float | Decimal) -> float:
    raw = float(quantity) * float(unit_price)
    discount = raw * (float(discount_percent) / 100)
    return round(raw - discount, 2)


async def _emit_quote_signal(
    db: AsyncSession | None,
    topic: str,
    organization_id: int,
    quote: Quote,
    *,
    actor_user_id: int | None = None,
    entity_id: str | None = None,
    payload_extra: dict | None = None,
) -> None:
    try:
        payload = {"quote_id": quote.id, "title": quote.title, "status": quote.status}
        if payload_extra:
            payload.update(payload_extra)
        await publish_signal(
            SignalEnvelope(
                topic=topic,
                category=SignalCategory.DOMAIN,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                source="quote.service",
                entity_type="quote",
                entity_id=entity_id or str(quote.id),
                payload=payload,
            ),
            db=db,
        )
    except Exception:
        logger.debug("Signal emission failed for %s quote_id=%s", topic, quote.id, exc_info=True)


async def _recalculate_quote_totals(db: AsyncSession, quote: Quote, organization_id: int) -> None:
    result = await db.execute(
        select(QuoteLineItem)
        .where(QuoteLineItem.quote_id == quote.id, QuoteLineItem.organization_id == organization_id)
    )
    items = list(result.scalars().all())
    subtotal = sum(float(i.line_total) for i in items)
    discount_amount = subtotal * (float(quote.discount_percent) / 100)
    after_discount = subtotal - discount_amount
    tax_amount = after_discount * (float(quote.tax_percent) / 100)
    quote.subtotal = round(subtotal, 2)
    quote.total = round(after_discount + tax_amount, 2)


async def get_quote(
    db: AsyncSession,
    quote_id: int,
    organization_id: int,
) -> Quote | None:
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id, Quote.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def list_quotes(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    deal_id: int | None = None,
    contact_id: int | None = None,
) -> list[Quote]:
    query = select(Quote).where(Quote.organization_id == organization_id)
    if status is not None:
        query = query.where(Quote.status == status)
    if deal_id is not None:
        query = query.where(Quote.deal_id == deal_id)
    if contact_id is not None:
        query = query.where(Quote.contact_id == contact_id)
    query = query.order_by(Quote.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_quote(
    db: AsyncSession,
    data: QuoteCreate,
    organization_id: int,
    *,
    created_by_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> Quote:
    payload = data.model_dump(exclude={"line_items"})
    payload.pop("line_items", None)
    quote = Quote(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        subtotal=0,
        total=0,
        **payload,
    )
    db.add(quote)
    await db.flush()
    for item_data in data.line_items:
        line_total = _line_total(
            item_data.quantity,
            item_data.unit_price,
            item_data.discount_percent,
        )
        item = QuoteLineItem(
            organization_id=organization_id,
            quote_id=quote.id,
            product_id=item_data.product_id,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            discount_percent=item_data.discount_percent,
            line_total=line_total,
        )
        db.add(item)
    await _recalculate_quote_totals(db, quote, organization_id)
    await db.commit()
    await db.refresh(quote)
    await _emit_quote_signal(db, QUOTE_CREATED, organization_id, quote, actor_user_id=created_by_user_id)
    logger.info("quote created id=%d org=%d", quote.id, organization_id)
    return quote


async def update_quote(
    db: AsyncSession,
    quote_id: int,
    data: QuoteUpdate,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
) -> Quote | None:
    quote = await get_quote(db, quote_id, organization_id)
    if quote is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key not in _PROTECTED_QUOTE_FIELDS and key in _QUOTE_UPDATE_FIELDS:
            setattr(quote, key, value)
    await _recalculate_quote_totals(db, quote, organization_id)
    await db.commit()
    await db.refresh(quote)
    await _emit_quote_signal(db, QUOTE_UPDATED, organization_id, quote, actor_user_id=actor_user_id)
    logger.info("quote updated id=%d org=%d", quote_id, organization_id)
    return quote


async def add_line_item(
    db: AsyncSession,
    quote_id: int,
    data: QuoteLineItemCreate,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
) -> QuoteLineItem | None:
    quote = await get_quote(db, quote_id, organization_id)
    if quote is None:
        return None
    line_total = _line_total(data.quantity, data.unit_price, data.discount_percent)
    item = QuoteLineItem(
        organization_id=organization_id,
        quote_id=quote_id,
        product_id=data.product_id,
        description=data.description,
        quantity=data.quantity,
        unit_price=data.unit_price,
        discount_percent=data.discount_percent,
        line_total=line_total,
    )
    db.add(item)
    await db.flush()
    await _recalculate_quote_totals(db, quote, organization_id)
    await db.commit()
    await db.refresh(item)
    await _emit_quote_signal(
        db, QUOTE_LINE_ITEM_ADDED, organization_id, quote,
        entity_id=str(item.id),
        payload_extra={"line_item_id": item.id},
        actor_user_id=actor_user_id,
    )
    return item


async def get_line_item(
    db: AsyncSession,
    line_item_id: int,
    quote_id: int,
    organization_id: int,
) -> QuoteLineItem | None:
    result = await db.execute(
        select(QuoteLineItem).where(
            QuoteLineItem.id == line_item_id,
            QuoteLineItem.quote_id == quote_id,
            QuoteLineItem.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_line_item(
    db: AsyncSession,
    quote_id: int,
    line_item_id: int,
    data: QuoteLineItemUpdate,
    organization_id: int,
) -> QuoteLineItem | None:
    item = await get_line_item(db, line_item_id, quote_id, organization_id)
    if item is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(item, key):
            setattr(item, key, value)
    qty = item.quantity
    up = float(item.unit_price)
    dp = float(item.discount_percent)
    item.line_total = _line_total(qty, up, dp)
    quote = await get_quote(db, quote_id, organization_id)
    if quote:
        await _recalculate_quote_totals(db, quote, organization_id)
    await db.commit()
    await db.refresh(item)
    return item


async def remove_line_item(
    db: AsyncSession,
    quote_id: int,
    line_item_id: int,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
) -> bool:
    item = await get_line_item(db, line_item_id, quote_id, organization_id)
    if item is None:
        return False
    quote = await get_quote(db, quote_id, organization_id)
    if quote is None:
        return False
    await db.delete(item)
    await _recalculate_quote_totals(db, quote, organization_id)
    await db.commit()
    await _emit_quote_signal(
        db, QUOTE_LINE_ITEM_REMOVED, organization_id, quote,
        entity_id=str(line_item_id),
        payload_extra={"line_item_id": line_item_id},
        actor_user_id=actor_user_id,
    )
    return True


async def list_line_items(
    db: AsyncSession,
    quote_id: int,
    organization_id: int,
) -> list[QuoteLineItem]:
    result = await db.execute(
        select(QuoteLineItem)
        .where(
            QuoteLineItem.quote_id == quote_id,
            QuoteLineItem.organization_id == organization_id,
        )
        .order_by(QuoteLineItem.id)
    )
    return list(result.scalars().all())
