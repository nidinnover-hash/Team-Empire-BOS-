"""Schemas for DecisionCard CRUD."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DecisionCategory = Literal["general", "strategic", "operational", "financial", "hr"]
DecisionUrgency = Literal["low", "normal", "high", "critical"]
DecisionStatus = Literal["pending", "decided", "deferred", "expired"]


class DecisionOption(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    description: str | None = None
    risk_level: str | None = None  # low | medium | high


class DecisionCardCreate(BaseModel):
    workspace_id: int
    title: str = Field(min_length=1, max_length=200)
    context_summary: str = Field(min_length=1, max_length=5000)
    options: list[DecisionOption] = Field(min_length=2, max_length=6)
    recommendation: str | None = Field(default=None, max_length=200)
    category: DecisionCategory = "general"
    urgency: DecisionUrgency = "normal"
    source_type: str | None = None
    source_id: str | None = None
    expires_at: datetime | None = None


class DecisionCardDecide(BaseModel):
    chosen_option: str = Field(min_length=1, max_length=200)
    decision_rationale: str | None = Field(default=None, max_length=2000)


class DecisionCardDefer(BaseModel):
    decision_rationale: str | None = Field(default=None, max_length=2000)


class DecisionCardRead(BaseModel):
    id: int
    organization_id: int
    workspace_id: int
    title: str
    context_summary: str
    options_json: str
    recommendation: str | None
    category: str
    urgency: str
    status: str
    chosen_option: str | None
    decision_rationale: str | None
    decided_by: int | None
    proposed_by: int | None
    source_type: str | None
    source_id: str | None
    created_at: datetime
    decided_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True}
