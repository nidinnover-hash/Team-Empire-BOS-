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
    failure_streak: int = 0
    retry_backoff_seconds: int | None = None
    suggested_next_retry_at: datetime | None = None
    dead_letter_candidate: bool = False


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
    state: Literal["healthy", "degraded", "stale", "down"]
    health_score: int = Field(default=0, ge=0, le=100)
    last_sync_status: str | None = None
    last_sync_at: datetime | None = None
    stale: bool
    age_hours: float | None = None
    token_age_days: int | None = None
    sync_error_rate_24h: float | None = Field(default=None, ge=0.0, le=1.0)
    recent_failures_24h: int = 0
    rate_limit_state: Literal["ok", "elevated", "unknown"] = "unknown"
    suggested_actions: list[str] = Field(default_factory=list)


class IntegrationHealthRead(BaseModel):
    generated_at: datetime
    stale_hours_threshold: int
    total_connected: int
    failing_count: int
    stale_count: int
    overall_health_score: int = Field(default=0, ge=0, le=100)
    items: list[IntegrationHealthItem]


class SystemHealthDependency(BaseModel):
    name: str
    status: Literal["ok", "degraded", "down", "not_configured"]
    detail: str


class SystemHealthRead(BaseModel):
    generated_at: datetime
    overall_status: Literal["ok", "degraded", "down"]
    dependencies: list[SystemHealthDependency]
    integrations: IntegrationHealthRead


class StorageMetricsRead(BaseModel):
    generated_at: datetime
    memory_context_cache: dict[str, int]
    ai_router_recent_calls_1h: int = 0
    ai_router_fallback_rate_1h: float = Field(default=0.0, ge=0.0, le=1.0)
    ai_router_errors_1h: int = 0
    ai_router_provider_counts_1h: dict[str, int] = Field(default_factory=dict)
    approval_feedback_stats: dict[str, float | int] = Field(default_factory=dict)


class SecurityPostureRead(BaseModel):
    generated_at: datetime
    status: Literal["ok", "needs_attention"]
    premium_mode: bool
    privacy_profile: str
    legal_terms_version: str | None = None
    account_mfa_required: bool
    account_sso_required: bool
    account_session_max_hours: int
    marketing_export_pii_allowed: bool
    open_issues: list[str]


class TrendMetricsRead(BaseModel):
    """Trend telemetry counter values."""
    model_config = {"extra": "allow"}


class SchedulerSLORead(BaseModel):
    window_hours: int
    total_runs: int
    success_rate: float
    p95_duration_ms: int
    stale_runs: int
    slo_breached: bool
    error_type_counts: dict[str, int] = Field(default_factory=dict)


class WebhookReliabilityRead(BaseModel):
    window_hours: int
    total_deliveries: int
    success_count: int
    failed_count: int
    dead_letter_count: int
    replayed_original_count: int
    replay_success_count: int
    error_category_counts: dict[str, int] = Field(default_factory=dict)


class BackupCreateRead(BaseModel):
    ok: bool = True
    path: str | None = None
    size_bytes: int | None = None
    error: str | None = None


class BackupListRead(BaseModel):
    count: int
    backups: list[dict]


class CronHealthRead(BaseModel):
    model_config = {"extra": "allow"}


class ExecutePlanRequest(BaseModel):
    challenge: str | None = None
    week_start_date: datetime | None = None


class ExecutePlanRead(BaseModel):
    ok: bool
    sync: dict
    email_control: dict
    compliance: dict
    dispatch_plan: list[dict]
    data_quality: dict


class DataQualityRead(BaseModel):
    generated_at: datetime
    missing_identity_count: int
    stale_metrics_count: int
    duplicate_identity_conflicts: int
    orphan_approval_count: int
    details: dict


class ManagerSLARead(BaseModel):
    generated_at: datetime
    missing_reports: int
    pending_approvals_breached: int
    status: str
    details: dict


class ScenarioSimulationRequest(BaseModel):
    challenge: str = Field(..., min_length=4, max_length=2000)
    blockers_count: int = Field(..., ge=1, le=200)
    top_n: int = Field(default=3, ge=1, le=10)


class ScenarioSimulationRead(BaseModel):
    challenge: str
    blockers_count: int
    baseline_risk_score: float
    projected_risk_score: float
    projected_risk_drop_percent: float
    recommended_dispatch: list[dict]


class WeeklyBoardPacketRead(BaseModel):
    generated_at: datetime
    week_start: str
    compliance: dict
    clone_summary: dict
    sla: dict
    data_quality: dict
    top_actions: list[str]


class MultiOrgCockpitOrgRead(BaseModel):
    org_id: int
    org_name: str
    clone_summary: dict
    compliance_open_count: int
    data_quality: dict


class MultiOrgCockpitRead(BaseModel):
    generated_at: datetime
    organizations: list[MultiOrgCockpitOrgRead]


class FounderPlaybookRead(BaseModel):
    generated_at: datetime
    core_values: list[str]
    north_star: str
    today_focus: list[str]
    people_growth_actions: list[str]
    strategic_growth_actions: list[str]
    evening_reflection: list[str]
    coaching_prompts: list[str]


class CEOMorningBriefRead(BaseModel):
    generated_at: datetime
    priority_actions: list[str]
    risk_snapshot: dict
    mode: Literal["suggest_only"]


class RecommendationConfidenceRead(BaseModel):
    score: int = Field(ge=0, le=100)
    level: Literal["low", "medium", "high"]
    reasons: list[str]
    needs_human_review: bool


class CEODailyBriefActionRead(BaseModel):
    title: str
    owner: Literal["nidin", "admin", "sharon", "mano"]
    priority: Literal["high", "medium", "low"]
    source: str
    confidence: RecommendationConfidenceRead


class CEODailyBriefRead(BaseModel):
    generated_at: datetime
    summary: dict
    top_actions: list[CEODailyBriefActionRead]
    mode: Literal["suggest_only"]


class BrainTrainRequest(BaseModel):
    challenge: str = Field(default="Increase execution quality with strict data-driven coaching.", min_length=8, max_length=2000)
    weeks: int = Field(default=1, ge=1, le=12)


class BrainTrainRead(BaseModel):
    ok: bool
    mode: Literal["suggest_only"]
    data_collection: dict
    metrics: dict
    clone_training: dict
    ceo_brain: dict


class CloneSelfDevelopRequest(BaseModel):
    challenge: str = Field(
        default="Identify clone limitations and propose a practical self-improvement plan.",
        min_length=8,
        max_length=2000,
    )
    week_start_date: datetime | None = None


class CloneLimitationRead(BaseModel):
    name: str
    severity: Literal["low", "medium", "high", "critical"]
    impact: str
    evidence: str


class CloneSelfDevelopRead(BaseModel):
    ok: bool
    mode: Literal["suggest_only"]
    provider: str
    limitations: list[CloneLimitationRead]
    development_plan: str
    next_actions: list[str]
    diagnostics: dict
