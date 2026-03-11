"""Quote / proposal endpoints."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.crm.bootstrap import quotes_enabled
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.services import quote as svc

router = APIRouter(prefix="/quotes", tags=["quotes"])


async def _require_quotes(db: AsyncSession, org_id: int) -> None:
    if not await quotes_enabled(db, org_id):
        raise HTTPException(status_code=404, detail="Not found")


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    title: str
    deal_id: int | None = None
    contact_id: int | None = None
    status: str
    subtotal: float
    discount_percent: float
    tax_percent: float
    total: float
    currency: str
    expiry_date: date | None = None
    notes: str | None = None
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class QuoteCreate(BaseModel):
    title: str
    deal_id: int | None = None
    contact_id: int | None = None
    status: str = "draft"
    discount_percent: float = 0
    tax_percent: float = 0
    currency: str = "USD"
    expiry_date: date | None = None
    notes: str | None = None


class QuoteUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    discount_percent: float | None = None
    tax_percent: float | None = None
    expiry_date: date | None = None
    notes: str | None = None


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    quote_id: int
    product_id: int | None = None
    description: str
    quantity: int
    unit_price: float
    discount_percent: float
    line_total: float
    created_at: datetime


class LineItemCreate(BaseModel):
    description: str
    quantity: int = 1
    unit_price: float = 0
    discount_percent: float = 0
    product_id: int | None = None


@router.post("", response_model=QuoteOut, status_code=201)
async def create_quote(
    body: QuoteCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    await _require_quotes(db, actor["org_id"])
    row = await svc.create_quote(db, organization_id=actor["org_id"], created_by_user_id=actor["id"], **body.model_dump())
    await record_action(
        db,
        event_type="quote_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="quote",
        entity_id=row.id,
        payload_json={"title": row.title, "status": row.status},
    )
    return row


@router.get("", response_model=list[QuoteOut])
async def list_quotes(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    await _require_quotes(db, actor["org_id"])
    return await svc.list_quotes(db, actor["org_id"], status=status)


@router.get("/{quote_id}", response_model=QuoteOut)
async def get_quote(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    await _require_quotes(db, actor["org_id"])
    row = await svc.get_quote(db, quote_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Quote not found")
    return row


@router.put("/{quote_id}", response_model=QuoteOut)
async def update_quote(
    quote_id: int,
    body: QuoteUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    await _require_quotes(db, actor["org_id"])
    row = await svc.update_quote(db, quote_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Quote not found")
    await record_action(
        db,
        event_type="quote_updated",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="quote",
        entity_id=row.id,
    )
    return row


@router.delete("/{quote_id}", status_code=204)
async def delete_quote(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    await _require_quotes(db, actor["org_id"])
    ok = await svc.delete_quote(db, quote_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Quote not found")
    await record_action(
        db,
        event_type="quote_deleted",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="quote",
        entity_id=quote_id,
    )


@router.post("/{quote_id}/lines", response_model=LineItemOut, status_code=201)
async def add_line_item(
    quote_id: int,
    body: LineItemCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    await _require_quotes(db, actor["org_id"])
    row = await svc.add_line_item(db, organization_id=actor["org_id"], quote_id=quote_id, **body.model_dump())
    await record_action(
        db,
        event_type="quote_line_item_added",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="quote_line_item",
        entity_id=row.id,
        payload_json={"quote_id": quote_id},
    )
    return row


@router.get("/{quote_id}/lines", response_model=list[LineItemOut])
async def list_line_items(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    await _require_quotes(db, actor["org_id"])
    return await svc.list_line_items(db, actor["org_id"], quote_id)


@router.delete("/lines/{item_id}", status_code=204)
async def delete_line_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    await _require_quotes(db, actor["org_id"])
    ok = await svc.delete_line_item(db, item_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Line item not found")
    await record_action(
        db,
        event_type="quote_line_item_deleted",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="quote_line_item",
        entity_id=item_id,
    )
