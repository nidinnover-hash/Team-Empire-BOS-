from datetime import datetime

from pydantic import BaseModel, Field


class ApprovalRequestCreate(BaseModel):
    organization_id: int = 1
    approval_type: str = Field(..., max_length=100)
    payload_json: dict = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    note: str | None = Field(None, max_length=500)


class ApprovalRead(BaseModel):
    id: int
    organization_id: int
    requested_by: int
    approval_type: str
    payload_json: dict
    status: str
    approved_by: int | None
    approved_at: datetime | None
    executed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalTimelineItem(BaseModel):
    id: int
    approval_type: str
    status: str
    requested_by: int
    approved_by: int | None
    created_at: datetime
    approved_at: datetime | None
    is_risky: bool
    requires_yes_execute: bool

    model_config = {"from_attributes": True}


class ApprovalTimelineResponse(BaseModel):
    pending_count: int
    approved_count: int
    rejected_count: int
    items: list[ApprovalTimelineItem]
