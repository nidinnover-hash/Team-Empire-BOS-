from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowDefinitionStep(BaseModel):
    key: str | None = Field(default=None, max_length=120)
    name: str = Field(..., min_length=1, max_length=200)
    action_type: str = Field(..., min_length=1, max_length=100)
    integration: str | None = Field(default=None, max_length=50)
    params: dict = Field(default_factory=dict)
    requires_approval: bool = False


class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    trigger_mode: str = Field(default="manual", max_length=20)
    trigger_spec_json: dict = Field(default_factory=dict)
    defaults_json: dict = Field(default_factory=dict)
    risk_level: str = Field(default="medium", max_length=20)
    steps: list[WorkflowDefinitionStep] = Field(..., min_length=1, max_length=20)


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    trigger_mode: str | None = Field(default=None, max_length=20)
    trigger_spec_json: dict | None = None
    defaults_json: dict | None = None
    risk_level: str | None = Field(default=None, max_length=20)
    steps: list[WorkflowDefinitionStep] | None = Field(default=None, min_length=1, max_length=20)


class WorkflowDefinitionRead(BaseModel):
    id: int
    organization_id: int
    workspace_id: int | None
    name: str
    slug: str
    description: str | None
    status: str
    trigger_mode: str
    trigger_spec_json: dict
    steps_json: list
    defaults_json: dict
    risk_level: str
    version: int
    created_by: int | None
    updated_by: int | None
    published_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
