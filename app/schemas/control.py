from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthSummaryRead(BaseModel):
    open_tasks: int
    pending_approvals: int
    connected_integrations: int
    failing_integrations: int
    generated_at: str


class CEOOverdueTask(BaseModel):
    task_id: str
    name: str
    due_date: str


class CEOPRReviewItem(BaseModel):
    repo_name: str
    pr_number: int
    title: str
    author: str | None = None
    url: str | None = None


class CEOBranchProtectionIssue(BaseModel):
    repo_name: str
    is_protected: bool
    requires_reviews: bool
    required_checks_enabled: bool


class CEOInfraRisk(BaseModel):
    droplet_id: str
    name: str
    status: str | None = None
    backups_enabled: bool | None = None


class CEOCostAlert(BaseModel):
    platform: str
    latest_amount_usd: float
    previous_amount_usd: float
    delta_percent: float
    title: str


class CEOStatusRead(BaseModel):
    top_overdue_critical_tasks: list[CEOOverdueTask]
    prs_waiting_sharon_review: list[CEOPRReviewItem]
    branch_protection_issues: list[CEOBranchProtectionIssue]
    infra_risks: list[CEOInfraRisk]
    cost_alerts: list[CEOCostAlert]
    mode: Literal["suggest_only"]


class ComplianceViolationRead(BaseModel):
    platform: str
    severity: Literal["LOW", "MED", "HIGH", "CRITICAL"]
    title: str
    details: dict
    status: str
    created_at: str | None = None


class ComplianceRunRead(BaseModel):
    ok: bool
    compliance_score: int
    violations: list[ComplianceViolationRead]
    mode: Literal["suggest_only"]


class ComplianceReportRead(BaseModel):
    count: int
    violations: list[ComplianceViolationRead]


class MessageDraftRequest(BaseModel):
    to: Literal["mano", "sharon"]
    topic: str = Field(..., min_length=1, max_length=255)
    violations: list[dict] = Field(default_factory=list)


class MessageDraftRead(BaseModel):
    to: str
    message: str
    checklist: list[str]


class GitHubIdentityMapUpsertRequest(BaseModel):
    company_email: str = Field(..., min_length=5, max_length=320)
    github_login: str = Field(..., min_length=1, max_length=255)


class GitHubIdentityMapItem(BaseModel):
    company_email: str
    github_login: str
    updated_at: str


class GitHubIdentityMapListRead(BaseModel):
    count: int
    items: list[GitHubIdentityMapItem]


class GitHubIdentityMapUpsertRead(BaseModel):
    ok: bool
    company_email: str
    github_login: str


class SchedulerJobRunItem(BaseModel):
    id: int
    job_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    details: dict
    error: str | None = None


class SchedulerJobRunListRead(BaseModel):
    count: int
    items: list[SchedulerJobRunItem]


class SchedulerReplayRequest(BaseModel):
    job_name: Literal[
        "clickup_sync",
        "github_sync",
        "digitalocean_sync",
        "slack_sync",
        "google_calendar_sync",
        "compliance_run",
        "daily_ceo_summary",
        "full_sync",
    ]


class SchedulerReplayRead(BaseModel):
    ok: bool
    job_name: str
    result: dict | None = None
    error: str | None = None


class IntegrationHealthItem(BaseModel):
    type: str
    connected: bool
    last_sync_status: str | None = None
    last_sync_at: datetime | None = None
    stale: bool
    age_hours: float | None = None


class IntegrationHealthRead(BaseModel):
    generated_at: datetime
    stale_hours_threshold: int
    total_connected: int
    failing_count: int
    stale_count: int
    items: list[IntegrationHealthItem]
