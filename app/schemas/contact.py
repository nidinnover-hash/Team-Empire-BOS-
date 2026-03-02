from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

ContactRelationship = Literal["personal", "business", "family", "mentor", "other"]
PipelineStage = Literal["new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"]
LeadSource = Literal["manual", "social_media", "referral", "website", "email", "event", "other"]


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
    expected_close_date: datetime | None
    last_contacted_at: datetime | None
    next_follow_up_at: datetime | None
    tags: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineSummary(BaseModel):
    stage: str
    count: int
    total_deal_value: float
