from datetime import datetime

from pydantic import BaseModel, Field


class GovernancePolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    policy_type: str = Field("general", max_length=50)
    rules_json: dict = Field(default_factory=dict)
    requires_ceo_approval: bool = True


class GovernancePolicyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    rules_json: dict | None = None
    is_active: bool | None = None


class GovernancePolicyRead(BaseModel):
    id: int
    organization_id: int
    name: str
    description: str | None
    policy_type: str
    rules_json: dict
    is_active: bool
    requires_ceo_approval: bool
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GovernanceViolationRead(BaseModel):
    id: int
    organization_id: int
    policy_id: int
    employee_id: int | None
    violation_type: str
    details_json: dict
    status: str
    resolved_by: int | None
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ComplianceSummary(BaseModel):
    total_policies: int
    active_policies: int
    total_violations: int
    open_violations: int
    resolved_violations: int
    compliance_rate: float


class AutomationLevel(BaseModel):
    """Tracks the progressive automation level for the organization."""
    current_level: float  # 0.05 to 0.95
    human_control: float  # 1.0 - current_level
    data_confidence: float
    recommendations_applied: int
    recommendations_total: int
    policy_compliance_rate: float
    suggested_next_level: float
    reasoning: str


class PolicyDriftSignalRead(BaseModel):
    policy_id: int
    policy_name: str
    metric: str
    baseline: float
    current: float
    threshold: float | None = None
    drift_percent: float
    below_threshold: bool
    severity: str
    open_violation_count: int
    recommendation: str


class PolicyDriftReportRead(BaseModel):
    generated_at: datetime
    window_days: int
    status: str
    signals: list[PolicyDriftSignalRead]


class PolicyDriftTrendPointRead(BaseModel):
    timestamp: datetime
    max_drift_percent: float
    signal_count: int


class PolicyDriftTrendRead(BaseModel):
    points: list[PolicyDriftTrendPointRead]
    next_cursor: str | None = None
