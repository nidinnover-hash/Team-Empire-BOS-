from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IntelligenceStatus = Literal["submitted", "reviewing", "accepted", "rejected", "applied"]
IntelligencePriority = Literal["low", "medium", "high", "critical"]
IntelligenceCategory = Literal[
    "market_demand",
    "campaign_feedback",
    "lead_quality",
    "offer_insight",
    "country_signal",
    "other",
]


class MarketingIntelligenceCreate(BaseModel):
    category: IntelligenceCategory = "other"
    title: str = Field(..., min_length=3, max_length=200)
    summary: str = Field(..., min_length=3, max_length=4000)
    confidence: float | None = Field(None, ge=0, le=1)
    priority: IntelligencePriority | None = None
    suggested_action: str | None = Field(None, max_length=4000)


class MarketingIntelligenceReview(BaseModel):
    status: IntelligenceStatus = "reviewing"
    create_decision_card: bool = False
    workspace_id: int | None = Field(None, ge=1)


class MarketingIntelligenceRead(BaseModel):
    id: int
    owner_company_id: int
    source_company_id: int
    category: IntelligenceCategory
    title: str
    summary: str
    confidence: float | None
    priority: IntelligencePriority | None
    suggested_action: str | None
    status: IntelligenceStatus
    created_by_user_id: int | None
    reviewed_by_user_id: int | None
    created_at: datetime
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}


class CockpitCount(BaseModel):
    key: str
    count: int
    label: str | None = None


class EmpireDigitalCockpitRead(BaseModel):
    total_visible_leads: int
    new_leads: int
    unrouted_leads: int
    routed_leads: int
    stale_unrouted_leads: int
    by_lead_type: list[CockpitCount]
    by_routed_company: list[CockpitCount]
    qualification_breakdown: list[CockpitCount]
    top_sources: list[CockpitCount]
    unrouted_aging_buckets: list[CockpitCount]
    average_routing_hours: float | None
    pending_intelligence: int
    stale_warning_triggered: bool = False
    stale_warning_threshold_count: int = 0
    warning_unrouted_threshold_count: int = 0
    visibility_scope: Literal["cross_company", "empire", "company_scoped"]


class MarketingIntelligenceReviewResult(BaseModel):
    item: MarketingIntelligenceRead
    decision_card_id: int | None = None


class FounderReportDailyPoint(BaseModel):
    day: str
    leads_created: int
    leads_routed: int
    stale_unrouted: int
    intelligence_accepted: int
    intelligence_rejected: int
    escalations_created: int = 0


class FounderFlowReportRead(BaseModel):
    window_days: int
    points: list[FounderReportDailyPoint]
