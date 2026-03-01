"""Schemas for automation triggers and workflows."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ── Automation Triggers ──────────────────────────────────────────────────────


class TriggerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    source_event: str = Field(..., min_length=1, max_length=100)
    source_integration: str | None = Field(None, max_length=50)
    filter_json: dict = Field(default_factory=dict)
    action_type: str = Field(..., min_length=1, max_length=100)
    action_integration: str | None = Field(None, max_length=50)
    action_params: dict = Field(default_factory=dict)
    requires_approval: bool = False


class TriggerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None
    filter_json: dict | None = None
    action_params: dict | None = None
    requires_approval: bool | None = None


class TriggerRead(BaseModel):
    id: int
    organization_id: int
    name: str
    description: str | None
    source_event: str
    source_integration: str | None
    filter_json: dict
    action_type: str
    action_integration: str | None
    action_params: dict
    is_active: bool
    requires_approval: bool
    fire_count: int
    last_fired_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Workflows ────────────────────────────────────────────────────────────────


class WorkflowStepDef(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    action_type: str = Field(..., min_length=1, max_length=100)
    integration: str | None = None
    params: dict = Field(default_factory=dict)
    requires_approval: bool = False


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    steps: list[WorkflowStepDef] = Field(..., min_length=1, max_length=20)


class WorkflowRead(BaseModel):
    id: int
    organization_id: int
    name: str
    description: str | None
    steps_json: list
    status: str
    current_step: int
    result_json: dict
    error_text: str | None
    created_by: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
