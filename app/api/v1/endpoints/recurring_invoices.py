"""Recurring invoices — scheduled invoice generation from templates."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import recurring_invoice as inv_service

router = APIRouter(prefix="/recurring-invoices", tags=["Recurring Invoices"])


class RecurringInvoiceCreate(BaseModel):
    title: str = Field(..., max_length=300)
    amount: float = Field(..., gt=0)
    currency: str = Field("USD", max_length=3)
    frequency: str = Field(..., pattern=r"^(weekly|monthly|quarterly|yearly)$")
    contact_id: int | None = None
    line_items: list[dict] = Field(default_factory=list)
    next_due_date: datetime | None = None


class RecurringInvoiceUpdate(BaseModel):
    title: str | None = Field(None, max_length=300)
    amount: float | None = Field(None, gt=0)
    frequency: str | None = Field(None, pattern=r"^(weekly|monthly|quarterly|yearly)$")
    next_due_date: datetime | None = None
    is_active: bool | None = None


class RecurringInvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    amount: float
    currency: str
    frequency: str
    contact_id: int | None = None
    line_items_json: str
    next_due_date: datetime | None = None
    last_generated_at: datetime | None = None
    total_generated: int
    is_active: bool
    created_at: datetime | None = None


@router.get("", response_model=list[RecurringInvoiceRead])
async def list_recurring_invoices(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[RecurringInvoiceRead]:
    items = await inv_service.list_recurring_invoices(db, organization_id=actor["org_id"], active_only=active_only)
    return [RecurringInvoiceRead.model_validate(i, from_attributes=True) for i in items]


@router.post("", response_model=RecurringInvoiceRead, status_code=201)
async def create_recurring_invoice(
    data: RecurringInvoiceCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RecurringInvoiceRead:
    inv = await inv_service.create_recurring_invoice(
        db, organization_id=actor["org_id"], created_by=int(actor["id"]),
        title=data.title, amount=data.amount, currency=data.currency,
        frequency=data.frequency, contact_id=data.contact_id,
        line_items=data.line_items, next_due_date=data.next_due_date,
    )
    return RecurringInvoiceRead.model_validate(inv, from_attributes=True)


@router.patch("/{invoice_id}", response_model=RecurringInvoiceRead)
async def update_recurring_invoice(
    invoice_id: int,
    data: RecurringInvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RecurringInvoiceRead:
    inv = await inv_service.update_recurring_invoice(
        db, invoice_id=invoice_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="Recurring invoice not found")
    return RecurringInvoiceRead.model_validate(inv, from_attributes=True)


@router.delete("/{invoice_id}", status_code=204)
async def delete_recurring_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await inv_service.delete_recurring_invoice(db, invoice_id=invoice_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Recurring invoice not found")


@router.post("/{invoice_id}/generate", response_model=RecurringInvoiceRead)
async def mark_invoice_generated(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RecurringInvoiceRead:
    inv = await inv_service.mark_generated(db, invoice_id=invoice_id, organization_id=actor["org_id"])
    if inv is None:
        raise HTTPException(status_code=404, detail="Recurring invoice not found")
    return RecurringInvoiceRead.model_validate(inv, from_attributes=True)


@router.get("/due")
async def get_due_invoices(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[dict]:
    items = await inv_service.get_due_invoices(db, organization_id=actor["org_id"])
    return [{"id": i.id, "title": i.title, "amount": i.amount, "next_due_date": i.next_due_date.isoformat() if i.next_due_date else None} for i in items]
