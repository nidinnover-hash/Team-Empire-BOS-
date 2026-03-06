from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

ContactRelationship = Literal["personal", "business", "family", "mentor", "other"]
PipelineStage = Literal["new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"]
LeadSource = Literal["manual", "social_media", "referral", "website", "email", "event", "other"]
LeadType = Literal["general", "study_abroad", "recruitment"]
RoutingStatus = Literal["unrouted", "under_review", "routed", "accepted", "rejected", "closed"]
QualificationStatus = Literal["unqualified", "qualified", "disqualified", "needs_review"]


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    company: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=100)
    relationship: ContactRelationship = "personal"
    notes: str | None = Field(None, max_length=2000)
    pipeline_stage: PipelineStage = "new"
    lead_score: int = Field(0, ge=0, le=100)
    lead_source: LeadSource | None = None
    deal_value: float | None = Field(None, ge=0)
    lead_type: LeadType = "general"
    source_channel: str | None = Field(None, max_length=80)
    campaign_name: str | None = Field(None, max_length=200)
    partner_id: str | None = Field(None, max_length=120)
    expected_close_date: datetime | None = None
    tags: str | None = Field(None, max_length=500)


class ContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    company: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=100)
    relationship: ContactRelationship | None = None
    notes: str | None = Field(None, max_length=2000)
    pipeline_stage: PipelineStage | None = None
    lead_score: int | None = Field(None, ge=0, le=100)
    lead_source: LeadSource | None = None
    deal_value: float | None = Field(None, ge=0)
    lead_type: LeadType | None = None
    source_channel: str | None = Field(None, max_length=80)
    campaign_name: str | None = Field(None, max_length=200)
    partner_id: str | None = Field(None, max_length=120)
    qualified_score: int | None = Field(None, ge=0, le=100)
    qualified_status: QualificationStatus | None = None
    qualification_notes: str | None = Field(None, max_length=4000)
    expected_close_date: datetime | None = None
    last_contacted_at: datetime | None = None
    next_follow_up_at: datetime | None = None
    tags: str | None = Field(None, max_length=500)


class ContactRead(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    company: str | None
    role: str | None
    relationship: str
    notes: str | None
    pipeline_stage: str
    lead_score: int
    lead_source: str | None
    deal_value: float | None
    lead_owner_company_id: int
    routed_company_id: int | None
    lead_type: str
    routing_status: str
    routing_reason: str | None
    routing_source: str | None
    routing_rule_id: int | None
    routed_at: datetime | None
    routed_by_user_id: int | None
    source_channel: str | None
    campaign_name: str | None
    partner_id: str | None
    qualified_score: int | None
    qualified_status: str
    qualification_notes: str | None
    expected_close_date: datetime | None
    last_contacted_at: datetime | None
    next_follow_up_at: datetime | None
    tags: str | None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PipelineSummary(BaseModel):
    stage: str
    count: int
    total_deal_value: float


class LeadRouteRequest(BaseModel):
    lead_type: LeadType | None = None
    routed_company_id: int | None = Field(None, ge=1)
    routing_reason: str | None = Field(None, max_length=500)


class LeadRouteResponse(BaseModel):
    contact_id: int
    lead_owner_company_id: int
    routed_company_id: int | None
    lead_type: str
    routing_status: RoutingStatus
    routing_reason: str | None
    routing_source: str | None
    routing_rule_id: int | None
    routed_at: datetime | None
    routed_by_user_id: int | None


class LeadQualificationUpdate(BaseModel):
    lead_type: LeadType | None = None
    qualified_score: int | None = Field(None, ge=0, le=100)
    qualified_status: QualificationStatus | None = None
    qualification_notes: str | None = Field(None, max_length=4000)
    routing_status: RoutingStatus | None = None
