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
    exposure_risk_level: str
    privacy_guardrails: list[str]
    legal_guardrails: list[str]
    account_guardrails: list[str]
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


class EmployeeManagementLayerReport(BaseModel):
    window_days: int
    total_employees: int
    active_employees: int
    inactive_employees: int
    github_mapped_employees: int
    clickup_mapped_employees: int
    unmapped_employees: int
    open_tasks: int
    overdue_tasks: int
    management_score: int = Field(ge=0, le=100)
    top_risks: list[str]
    next_actions: list[str]


class RevenueManagementLayerReport(BaseModel):
    window_days: int
    income_in_window: float
    expense_in_window: float
    net_in_window: float
    recurring_expense_ratio: float
    revenue_health_score: int = Field(ge=0, le=100)
    top_risks: list[str]
    next_actions: list[str]


class StaffTrainingLayerReport(BaseModel):
    window_days: int
    active_staff: int
    avg_ai_level: float
    low_ai_level_staff: int
    open_training_tasks: int
    due_soon_training_tasks: int
    training_velocity_score: int = Field(ge=0, le=100)
    top_risks: list[str]
    next_actions: list[str]


class AISkillRoutingMember(BaseModel):
    name: str
    role_title: str | None = None
    ai_level: int = Field(ge=1, le=5)
    recommended_niche: str
    interest_signals: list[str]
    readiness_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    next_step: str


class AISkillRoutingLayerReport(BaseModel):
    window_days: int
    active_staff: int
    avg_ai_level: float
    routing_score: int = Field(ge=0, le=100)
    top_opportunities: list[str]
    members: list[AISkillRoutingMember]
    next_actions: list[str]


class StaffProsperityLayerReport(BaseModel):
    window_days: int
    active_staff: int
    opportunity_index: int = Field(ge=0, le=100)
    wealth_index: int = Field(ge=0, le=100)
    happiness_index: int = Field(ge=0, le=100)
    freedom_index: int = Field(ge=0, le=100)
    composite_score: int = Field(ge=0, le=100)
    top_risks: list[str]
    next_actions: list[str]
    ceo_message: str


class CloneTrainingMember(BaseModel):
    employee_id: int
    name: str
    job_title: str | None = None
    has_identity_map: bool
    has_clone_profile: bool
    latest_clone_score: float
    readiness_level: str
    training_plan_status: str
    next_training_action: str


class CloneTrainingLayerReport(BaseModel):
    window_days: int
    total_employees: int
    clone_ready_employees: int
    missing_profile_employees: int
    open_training_plans: int
    clone_training_score: int = Field(ge=0, le=100)
    top_risks: list[str]
    next_actions: list[str]
    members: list[CloneTrainingMember]


class CloneMarketingSalesMember(BaseModel):
    employee_id: int
    name: str
    job_title: str | None = None
    clone_score: float
    readiness_level: str
    lead_focus: str
    next_action: str


class CloneMarketingSalesLayerReport(BaseModel):
    window_days: int
    business_contacts_total: int
    new_business_contacts: int
    open_follow_up_tasks: int
    lead_pipeline_health_score: int = Field(ge=0, le=100)
    top_bottlenecks: list[str]
    next_actions: list[str]
    members: list[CloneMarketingSalesMember]


class OpportunityAssociationItem(BaseModel):
    contact_name: str
    company: str | None = None
    opportunity_theme: str
    fit_score: int = Field(ge=0, le=100)
    recommended_owner: str
    reasoning: str


class OpportunityAssociationLayerReport(BaseModel):
    window_days: int
    opportunities_found: int
    association_score: int = Field(ge=0, le=100)
    top_opportunities: list[OpportunityAssociationItem]
    next_actions: list[str]
