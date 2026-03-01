from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

VALID_WEBHOOK_EVENTS: set[str] = {
    "approval.created",
    "approval.approved",
    "approval.rejected",
    "task.created",
    "task.completed",
    "coaching_report.created",
    "coaching_report.approved",
    "coaching_report.rejected",
}


class WebhookEndpointCreate(BaseModel):
    url: str = Field(..., min_length=10, max_length=2048)
    description: str | None = Field(None, max_length=500)
    event_types: list[str] = Field(default_factory=list)
    max_retry_attempts: int = Field(5, ge=1, le=20)


class WebhookEndpointUpdate(BaseModel):
    url: str | None = Field(None, min_length=10, max_length=2048)
    description: str | None = Field(None, max_length=500)
    event_types: list[str] | None = None
    is_active: bool | None = None


class WebhookEndpointRead(BaseModel):
    id: int
    url: str
    description: str | None
    event_types: list[str]
    is_active: bool
    max_retry_attempts: int = 5
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookEndpointCreateResponse(BaseModel):
    id: int
    url: str
    description: str | None
    event_types: list[str]
    is_active: bool
    signing_secret: str
    created_at: datetime
    updated_at: datetime


class WebhookTestResponse(BaseModel):
    ok: bool
    status_code: int | None = None
    error: str | None = None
    duration_ms: int | None = None


class WebhookDeliveryRead(BaseModel):
    id: int
    event: str
    payload_json: dict
    status: str
    response_status_code: int | None
    error_message: str | None
    duration_ms: int | None
    attempt_count: int
    max_retries: int = 5
    next_retry_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryListResponse(BaseModel):
    count: int
    items: list[WebhookDeliveryRead]
