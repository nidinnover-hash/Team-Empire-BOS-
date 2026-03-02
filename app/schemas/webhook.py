from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

VALID_WEBHOOK_EVENTS: set[str] = {
    # Dot-separated (legacy / manual dispatch)
    "approval.created",
    "approval.approved",
    "approval.rejected",
    "task.created",
    "task.completed",
    "coaching_report.created",
    "coaching_report.approved",
    "coaching_report.rejected",
    # Underscore-separated (audit event bus)
    "task_created",
    "task_updated",
    "task_deleted",
    "approval_requested",
    "approval_approved",
    "approval_rejected",
    "approval_executed",
    "integration_connected",
    "integration_disconnected",
    "integration_tested",
    "execution_started",
    "execution_succeeded",
    "execution_failed",
    "trigger_created",
    "trigger_updated",
    "trigger_deleted",
    "workflow_created",
    "workflow_started",
    "workflow_advanced",
    "security_user_created",
    "security_user_role_changed",
    "security_user_active_toggled",
    "security_webhook_endpoint_created",
    "security_webhook_endpoint_updated",
    "security_webhook_endpoint_deleted",
    "security_webhook_dead_letter_replayed",
    "security_mfa_enabled",
    "security_mfa_disabled",
    "security_organization_created",
    "security_organization_updated",
    "security_feature_flags_updated",
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
    error_category: str | None = None
    duration_ms: int | None
    attempt_count: int
    max_retries: int = 5
    next_retry_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryListResponse(BaseModel):
    count: int
    items: list[WebhookDeliveryRead]


class WebhookReplayResponse(BaseModel):
    ok: bool
    replayed_delivery_id: int | None = None
    error: str | None = None
