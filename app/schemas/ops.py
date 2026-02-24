from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

DecisionType = Literal["approve", "reject", "defer"]
ReportType = Literal["team_health", "project_risk", "founder_review"]


# ---- Employee ----

class EmployeeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role: str | None = Field(None, max_length=100)
    email: str = Field(..., min_length=3, max_length=320)
    github_username: str | None = Field(None, max_length=100)
    clickup_user_id: str | None = Field(None, max_length=100)
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    role: str | None = Field(None, max_length=100)
    email: str | None = Field(None, min_length=3, max_length=320)
    github_username: str | None = None
    clickup_user_id: str | None = None
    is_active: bool | None = None


class EmployeeRead(BaseModel):
    id: int
    organization_id: int
    name: str
    role: str | None
    email: str
    github_username: str | None
    clickup_user_id: str | None
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
