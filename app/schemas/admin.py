"""Schemas for super-admin cross-org analytics."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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


class AutonomyPolicyUpdate(BaseModel):
    current_mode: Literal["suggest_only", "approved_execution", "autonomous"] | None = None
    allow_auto_approval: bool | None = None
    min_readiness_for_auto_approval: int | None = None
    min_readiness_for_approved_execution: int | None = None
    min_readiness_for_autonomous: int | None = None
    block_on_unread_high_alerts: bool | None = None
    block_on_stale_integrations: bool | None = None
    block_on_sla_breaches: bool | None = None
