"""Schemas for super-admin cross-org analytics."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OrgSummary(BaseModel):
    id: int
    name: str
    slug: str
    user_count: int
    task_count: int
    approval_count: int
    last_activity_at: datetime | None

    model_config = {"from_attributes": True}


class AdminUserRead(BaseModel):
    id: int
    organization_id: int
    name: str
    email: str
    role: str
    is_active: bool
    is_super_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgReadinessMetric(BaseModel):
    name: str
    value: int
    target: int
    status: Literal["ok", "warning", "critical"]


class OrgReadinessReport(BaseModel):
    org_id: int
    org_name: str
    score: int
    status: Literal["ready", "watch", "blocked"]
    blockers: list[str]
    recommendations: list[str]
    metrics: list[OrgReadinessMetric]
    generated_at: datetime


class OrgReadinessFleetItem(BaseModel):
    org_id: int
    org_name: str
    score: int
    status: Literal["ready", "watch", "blocked"]
    blocker_count: int
    generated_at: datetime


class AutonomyGatesRead(BaseModel):
    org_id: int
    org_name: str
    readiness_score: int
    readiness_status: Literal["ready", "watch", "blocked"]
    allowed_modes: list[Literal["suggest_only", "approved_execution", "autonomous"]]
    denied_modes: list[Literal["approved_execution", "autonomous"]]
    reasons: list[str]
    generated_at: datetime


class ReadinessTrendPoint(BaseModel):
    day: str
    integration_failures: int
    high_alerts_created: int
    pending_approvals_created: int


class ReadinessTrendRead(BaseModel):
    org_id: int
    org_name: str
    days: int
    series: list[ReadinessTrendPoint]
    generated_at: datetime


class WhatsAppWebhookFailureRead(BaseModel):
    event_id: int
    event_type: str
    error_code: str | None = None
    detail: str | None = None
    phone_number_id: str | None = None
    actor_user_id: int | None = None
    created_at: datetime


class WhatsAppWebhookFailureListRead(BaseModel):
    org_id: int
    org_name: str
    days: int
    total: int
    failures: list[WhatsAppWebhookFailureRead]
    generated_at: datetime


class AutonomyPolicyRead(BaseModel):
    current_mode: Literal["suggest_only", "approved_execution", "autonomous"]
    allow_auto_approval: bool
    min_readiness_for_auto_approval: int
    min_readiness_for_approved_execution: int
    min_readiness_for_autonomous: int
    block_on_unread_high_alerts: bool
    block_on_stale_integrations: bool
    block_on_sla_breaches: bool
    updated_at: datetime | None = None
    updated_by_user_id: int | None = None
    updated_by_email: str | None = None


class AutonomyPolicySnapshot(BaseModel):
    current_mode: Literal["suggest_only", "approved_execution", "autonomous"]
    allow_auto_approval: bool
    min_readiness_for_auto_approval: int
    min_readiness_for_approved_execution: int
    min_readiness_for_autonomous: int
    block_on_unread_high_alerts: bool
    block_on_stale_integrations: bool
    block_on_sla_breaches: bool


class AutonomyPolicyHistoryItemRead(BaseModel):
    version_id: str
    updated_at: datetime | None = None
    updated_by_user_id: int | None = None
    updated_by_email: str | None = None
    rollback_of_version_id: str | None = None
    policy: AutonomyPolicySnapshot


class AutonomyTemplateRead(BaseModel):
    id: str
    label: str
    description: str
    policy: AutonomyPolicySnapshot


class AutonomyRolloutRead(BaseModel):
    kill_switch: bool
    pilot_org_ids: list[int]
    max_actions_per_day: int


class AutonomyRolloutUpdate(BaseModel):
    kill_switch: bool | None = None
    pilot_org_ids: list[int] | None = Field(default=None, max_length=1000)
    max_actions_per_day: int | None = Field(default=None, ge=0)


class AutonomyDryRunRequest(BaseModel):
    approval_type: str = Field(min_length=1, max_length=100)
    payload_json: dict = Field(default_factory=dict)


class AutonomyDryRunRead(BaseModel):
    org_id: int
    org_name: str
    approval_type: str
    readiness_score: int
    readiness_status: Literal["ready", "watch", "blocked"]
    allowed_modes: list[Literal["suggest_only", "approved_execution", "autonomous"]]
    rollout_allowed: bool
    rollout_reason: str | None
    actions_today: int
    max_actions_per_day: int
    can_auto_approve: bool
    can_execute_after_approval: bool
    reasons: list[str]
    generated_at: datetime


class AutonomyPolicyUpdate(BaseModel):
    current_mode: Literal["suggest_only", "approved_execution", "autonomous"] | None = None
    allow_auto_approval: bool | None = None
    min_readiness_for_auto_approval: int | None = Field(default=None, ge=0, le=100)
    min_readiness_for_approved_execution: int | None = Field(default=None, ge=0, le=100)
    min_readiness_for_autonomous: int | None = Field(default=None, ge=0, le=100)
    block_on_unread_high_alerts: bool | None = None
    block_on_stale_integrations: bool | None = None
    block_on_sla_breaches: bool | None = None


class SuperAdminActionResponse(BaseModel):
    ok: bool
    user_id: int
    is_super_admin: bool
