from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

RiskTier = Literal["low", "medium", "high"]


class DecisionTraceCreate(BaseModel):
    organization_id: int
    trace_type: str = Field(..., max_length=100)
    title: str = Field(..., max_length=255)
    summary: str = Field(..., max_length=5000)
    confidence_score: float = Field(ge=0.0, le=1.0)
    signals_json: dict = Field(default_factory=dict)
    actor_user_id: int | None = None
    request_id: str | None = Field(None, max_length=100)
    daily_run_id: int | None = None
    source_event_id: int | None = None


class DecisionTraceRead(BaseModel):
    id: int
    organization_id: int
    trace_type: str
    title: str
    summary: str
    confidence_score: float
    risk_tier: RiskTier = "medium"
    reasoning: list[str] = Field(default_factory=list)
    signals_json: dict
    actor_user_id: int | None
    request_id: str | None = None
    daily_run_id: int | None
    source_event_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutiveSummaryRead(BaseModel):
    organization_id: int
    generated_at: datetime
    window_days: int
    decision_summary: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    risk_tier: RiskTier
    reasoning: list[str] = Field(default_factory=list)
    kpis: dict
    highlights: list[str]
    risks: list[str]
    action_recommendations: list[str]


class DailyChangeItem(BaseModel):
    metric: str
    yesterday: float
    today: float
    delta: float


class ExecutiveDiffRead(BaseModel):
    organization_id: int
    date_today: date
    date_yesterday: date
    changes: list[DailyChangeItem]
    what_changed_since_yesterday: str
    risk_increased: str
    opportunity_increased: str
    urgent_decision: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    risk_tier: RiskTier
    reasoning: list[str] = Field(default_factory=list)
    narrative: str
