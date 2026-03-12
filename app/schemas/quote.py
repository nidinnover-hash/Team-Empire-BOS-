"""Quote and line item schemas for CRM."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

QuoteStatus = Literal["draft", "sent", "accepted", "rejected", "expired"]


class QuoteLineItemCreate(BaseModel):
    product_id: int | None = None
    description: str = Field(..., min_length=1, max_length=500)
    quantity: int = Field(1, ge=1)
    unit_price: Decimal | float = Field(0, ge=0)
    discount_percent: Decimal | float = Field(0, ge=0, le=100)


class QuoteLineItemUpdate(BaseModel):
    description: str | None = Field(None, min_length=1, max_length=500)
    quantity: int | None = Field(None, ge=1)
    unit_price: Decimal | float | None = Field(None, ge=0)
    discount_percent: Decimal | float | None = Field(None, ge=0, le=100)


class QuoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    deal_id: int | None = None
    contact_id: int | None = None
    status: QuoteStatus = "draft"
    currency: str = Field("USD", max_length=10)
    discount_percent: Decimal | float = Field(0, ge=0, le=100)
    tax_percent: Decimal | float = Field(0, ge=0, le=100)
    expiry_date: date | None = None
    notes: str | None = None
    line_items: list[QuoteLineItemCreate] = Field(default_factory=list)


class QuoteUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    deal_id: int | None = None
    contact_id: int | None = None
    status: QuoteStatus | None = None
    currency: str | None = Field(None, max_length=10)
    discount_percent: Decimal | float | None = Field(None, ge=0, le=100)
    tax_percent: Decimal | float | None = Field(None, ge=0, le=100)
    expiry_date: date | None = None
    notes: str | None = None
