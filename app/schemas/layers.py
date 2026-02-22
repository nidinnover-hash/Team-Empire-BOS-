from pydantic import BaseModel, Field


class MarketingLayerReport(BaseModel):
    window_days: int
    business_contacts_total: int
    new_business_contacts: int
    open_follow_up_tasks: int
    ad_spend_in_window: float
    revenue_in_window: float
    spend_to_revenue_ratio: float
    readiness_score: int = Field(ge=0, le=100)
    bottlenecks: list[str]
    next_actions: list[str]


class StudyLayerReport(BaseModel):
    window_days: int
    study_pipeline_contacts: int
    open_study_tasks: int
    due_soon_study_tasks: int
    study_related_revenue: float
    operational_score: int = Field(ge=0, le=100)
    blockers: list[str]
    next_actions: list[str]


class TrainingLayerReport(BaseModel):
    window_days: int
    active_team_members: int
    avg_ai_level: float
    open_training_tasks: int
    due_soon_training_tasks: int
    recent_training_notes: int
    training_score: int = Field(ge=0, le=100)
    blockers: list[str]
    next_actions: list[str]


class EmployeePerformanceMember(BaseModel):
    name: str
    team: str | None = None
    role_title: str | None = None
    ai_level: int = Field(ge=1, le=5)
    readiness_score: int = Field(ge=0, le=100)
    risk_flags: list[str]


class EmployeePerformanceLayerReport(BaseModel):
    window_days: int
    active_team_members: int
    avg_ai_level: float
    low_ai_members: int
    high_ai_members: int
    open_operational_tasks: int
    overdue_operational_tasks: int
    blocker_events_in_window: int
    performance_score: int = Field(ge=0, le=100)
    top_risks: list[str]
    next_actions: list[str]
    members: list[EmployeePerformanceMember]
