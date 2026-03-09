"""Deal schemas for CRUD operations."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

DealStage = Literal["discovery", "proposal", "negotiation", "contract", "won", "lost"]


class DealCreate(BaseModel):
    contact_id: int | None = None
    title: str = Field(..., min_length=1, max_length=300)
    stage: DealStage = "discovery"
    value: float = Field(0, ge=0, le=999_999_999.99)
    currency: str = Field("USD", max_length=10)
    probability: int = Field(0, ge=0, le=100)
    expected_close_date: date | None = None
    description: str | None = Field(None, max_length=2000)
    source: str | None = Field(None, max_length=100)


class DealUpdate(BaseModel):
    contact_id: int | None = None
    title: str | None = Field(None, min_length=1, max_length=300)
    stage: DealStage | None = None
    value: float | None = Field(None, ge=0, le=999_999_999.99)
    probability: int | None = Field(None, ge=0, le=100)
    expected_close_date: date | None = None
    description: str | None = None
    source: str | None = None
    lost_reason: str | None = Field(None, max_length=500)


class DealRead(BaseModel):
    id: int
    organization_id: int
    contact_id: int | None
    title: str
    stage: str
    value: float
    currency: str
    probability: int
    expected_close_date: date | None
    description: str | None
    source: str | None
    owner_user_id: int | None
    won_at: datetime | None
    lost_at: datetime | None
    lost_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DealPipelineAnalytics(BaseModel):
    stage: str
    count: int
    total_value: float
    avg_value: float
    avg_probability: float


class DealSummary(BaseModel):
    total_deals: int
    total_value: float
    won_value: float
    lost_count: int
    win_rate: float
    avg_deal_size: float
    pipeline: list[DealPipelineAnalytics]
