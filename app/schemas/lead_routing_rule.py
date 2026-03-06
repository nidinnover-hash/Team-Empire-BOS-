from datetime import datetime

from pydantic import BaseModel, Field


class LeadRoutingRuleCreate(BaseModel):
    lead_type: str = Field(..., min_length=1, max_length=50)
    target_company_id: int = Field(..., ge=1)
    priority: int = Field(100, ge=1, le=1000)
    routing_reason: str | None = Field(None, max_length=500)


class LeadRoutingRuleUpdate(BaseModel):
    target_company_id: int | None = Field(None, ge=1)
    priority: int | None = Field(None, ge=1, le=1000)
    routing_reason: str | None = Field(None, max_length=500)
    is_active: bool | None = None


class LeadRoutingRuleRead(BaseModel):
    id: int
    owner_company_id: int
    lead_type: str
    target_company_id: int
    priority: int
    routing_reason: str | None
    is_active: bool
    created_by_user_id: int | None
    updated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
