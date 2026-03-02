from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

DecisionType = Literal["approve", "reject", "defer"]
ReportType = Literal["team_health", "project_risk", "founder_review"]


# ---- Daily Run Response ----

class DailyRunResponse(BaseModel):
    """Response for POST /ops/daily-run."""
    status: str
    message: str
    daily_run_id: int
    run_date: str
    team_filter: str
    idempotent_reuse: bool
    requires_approval: bool
    executive_summary: dict | None = None
    drafted_plan_count: int | None = None
    drafted_plan_ids: list[int] | None = None
    drafted_email_count: int | None = None
    drafted_email_ids: list[int] | None = None
    pending_approvals: int | None = None
    decision_trace_id: int | None = None
    confidence_score: float | None = None
    risk_tier: str | None = None
    confidence_reasoning: list[str] | None = None


class IncidentCommandRead(BaseModel):
    generated_at: datetime
    incident_level: Literal["green", "amber", "red"]
    score: int
    triggers: dict[str, int]
    top_actions: list[str]
    status: str


class IncidentCommandTrendPointRead(BaseModel):
    timestamp: datetime
    score: int
    incident_level: Literal["green", "amber", "red"]


class IncidentCommandTrendRead(BaseModel):
    points: list[IncidentCommandTrendPointRead]
    next_cursor: str | None = None


# ---- Weekly Metrics Response ----

class WeeklyMetricsResponse(BaseModel):
    """Response for POST /ops/compute/weekly-metrics."""
    weeks_computed: int = 0
    employees_processed: int = 0
    task_metrics: int = 0
    code_metrics: int = 0
    comms_metrics: int = 0


# ---- Sync Result ----

class SyncResultRead(BaseModel):
    """Standard response for /ops/sync/* endpoints."""
    synced: int = 0
    error: str | None = None


class CicdSyncResultRead(BaseModel):
    """Response for /ops/sync/github-cicd endpoint."""
    workflow_runs: int = 0
    deployments: int = 0
    error: str | None = None


# ---- Employee ----

class EmployeeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role: str | None = Field(None, max_length=100)
    email: str = Field(..., min_length=3, max_length=320)
    department_id: int | None = None
    github_username: str | None = Field(None, max_length=100)
    clickup_user_id: str | None = Field(None, max_length=100)
    employment_status: str = Field("active", max_length=20)
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    role: str | None = Field(None, max_length=100)
    email: str | None = Field(None, min_length=3, max_length=320)
    department_id: int | None = None
    github_username: str | None = None
    clickup_user_id: str | None = None
    employment_status: str | None = Field(None, max_length=20)
    is_active: bool | None = None


class EmployeeRead(BaseModel):
    id: int
    organization_id: int
    department_id: int | None = None
    name: str
    role: str | None
    email: str
    github_username: str | None
    clickup_user_id: str | None
    employment_status: str = "active"
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- Decision Log ----

class DecisionLogCreate(BaseModel):
    decision_type: DecisionType
    context: str = Field(..., min_length=1, max_length=5000)
    objective: str = Field(..., min_length=1, max_length=2000)
    constraints: str | None = Field(None, max_length=2000)
    deadline: str | None = Field(None, max_length=100)
    success_metric: str | None = Field(None, max_length=2000)
    reason: str = Field(..., min_length=1, max_length=5000)
    risk: str | None = Field(None, max_length=2000)


class DecisionLogRead(BaseModel):
    id: int
    organization_id: int
    decision_type: str
    context: str
    objective: str
    constraints: str | None
    deadline: str | None
    success_metric: str | None
    reason: str
    risk: str | None
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Weekly Report ----

class WeeklyReportRead(BaseModel):
    id: int
    organization_id: int
    week_start_date: date
    report_type: str
    content_markdown: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Policy Rule ----

class PolicyRuleRead(BaseModel):
    id: int
    organization_id: int
    title: str
    rule_text: str
    examples_json: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Metrics (read-only) ----

class TaskMetricRead(BaseModel):
    id: int
    employee_id: int
    week_start_date: date
    tasks_assigned: int
    tasks_completed: int
    on_time_rate: float
    avg_cycle_time_hours: float
    reopen_count: int
    notes: str | None

    model_config = {"from_attributes": True}


class CodeMetricRead(BaseModel):
    id: int
    employee_id: int
    week_start_date: date
    commits: int
    prs_opened: int
    prs_merged: int
    reviews_done: int
    issue_links: int
    files_touched_count: int

    model_config = {"from_attributes": True}


class CommsMetricRead(BaseModel):
    id: int
    employee_id: int
    week_start_date: date
    emails_sent: int
    emails_replied: int
    median_reply_time_minutes: float
    escalation_count: int

    model_config = {"from_attributes": True}


class CloneScoreRead(BaseModel):
    id: int
    organization_id: int
    employee_id: int
    week_start_date: date
    productivity_score: float
    quality_score: float
    collaboration_score: float
    learning_score: float
    overall_score: float
    readiness_level: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CloneTrainingRunRead(BaseModel):
    week_start_date: str
    employees_scored: int


class CloneSummaryRead(BaseModel):
    count: int
    avg_score: float
    elite: int
    strong: int
    developing: int
    needs_support: int


class CloneDispatchRequest(BaseModel):
    challenge: str = Field(..., min_length=4, max_length=2000)
    week_start_date: date | None = None
    top_n: int = Field(default=3, ge=1, le=10)


class CloneDispatchItemRead(BaseModel):
    employee_id: int
    employee_name: str
    role: str | None
    overall_score: float
    readiness_level: str
    fit_reason: str


class EmployeeIdentityMapUpsert(BaseModel):
    employee_id: int = Field(..., ge=1)
    work_email: str | None = None
    github_login: str | None = None
    clickup_user_id: str | None = None
    slack_user_id: str | None = None


class EmployeeIdentityMapRead(BaseModel):
    id: int
    organization_id: int
    employee_id: int
    work_email: str | None
    github_login: str | None
    clickup_user_id: str | None
    slack_user_id: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class CloneProfileUpsert(BaseModel):
    employee_id: int = Field(..., ge=1)
    strengths: list[str] = Field(default_factory=list)
    weak_zones: list[str] = Field(default_factory=list)
    preferred_task_types: list[str] = Field(default_factory=list)


class CloneProfileRead(BaseModel):
    id: int
    organization_id: int
    employee_id: int
    strengths: list[str]
    weak_zones: list[str]
    preferred_task_types: list[str]
    updated_at: datetime


class CloneFeedbackCreate(BaseModel):
    employee_id: int = Field(..., ge=1)
    source_type: Literal["task", "approval", "email"]
    source_id: int | None = None
    outcome_score: float = Field(..., ge=0.0, le=1.0)
    notes: str | None = Field(None, max_length=2000)


class RoleTrainingPlanRead(BaseModel):
    id: int
    organization_id: int
    employee_id: int
    week_start_date: date
    role_focus: str
    plan_markdown: str
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleTrainingPlanStatusUpdate(BaseModel):
    status: Literal["OPEN", "DONE"]
