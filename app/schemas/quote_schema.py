"""Quote and quote line item schemas for CRM quote endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

QuoteStatus = Literal["draft", "sent", "accepted", "rejected", "expired"]


class QuoteLineItemCreate(BaseModel):
    """Schema for creating a single line item on a quote."""

    product_id: UUID = Field(..., description="Reference to the product")
    quantity: int = Field(..., ge=1, le=999_999, description="Quantity ordered")
    unit_price: Decimal = Field(..., ge=0, decimal_places=2, description="Price per unit")
    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, decimal_places=2, description="Discount percentage (0-100)"
    )

    @field_validator("unit_price", "discount_percent", mode="before")
    @classmethod
    def _coerce_decimal(cls, v):
        if v is not None and not isinstance(v, Decimal):
            return Decimal(str(v))
        return v


class QuoteLineItemRead(BaseModel):
    """Schema for reading a quote line item (ORM-friendly)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    quantity: int
    unit_price: Decimal
    discount_percent: Decimal
    line_total: Decimal
    created_at: datetime


class QuoteCreate(BaseModel):
    """Schema for creating a quote."""

    client_name: str = Field(..., min_length=1, max_length=255, description="Name of the client")
    amount: Decimal = Field(..., ge=0, decimal_places=2, description="Total quote amount")
    status: QuoteStatus = Field(default="draft", description="Quote status")
    valid_until: datetime | None = Field(None, description="Quote validity expiry")
    notes: str | None = Field(None, max_length=2000, description="Optional notes")

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, v):
        if v is not None and not isinstance(v, Decimal):
            return Decimal(str(v))
        return v


class QuoteRead(BaseModel):
    """Schema for reading a full quote with line items."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_name: str
    amount: Decimal
    status: str
    valid_until: datetime | None
    notes: str | None
    line_items: list[QuoteLineItemRead] = Field(default_factory=list, description="Quote line items")
    created_at: datetime
    updated_at: datetime


class QuoteUpdate(BaseModel):
    """Schema for updating a quote; all fields optional."""

    client_name: str | None = Field(None, min_length=1, max_length=255)
    amount: Decimal | None = Field(None, ge=0, decimal_places=2)
    status: QuoteStatus | None = None
    valid_until: datetime | None = None
    notes: str | None = Field(None, max_length=2000)

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, v):
        if v is None:
            return v
        if not isinstance(v, Decimal):
            return Decimal(str(v))
        return v


class QuoteListRead(BaseModel):
    """Schema for quote list views (summary fields only)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_name: str
    amount: Decimal
    status: str
    created_at: datetime
