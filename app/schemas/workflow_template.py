from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowTemplateRead(BaseModel):
    id: int
    organization_id: int | None
    workspace_id: int | None
    template_key: str
    name: str
    description: str | None
    category: str
    is_system: bool
    is_active: bool
    pack_version: int
    definition_json: dict
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowTemplateInstantiateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    workspace_id: int | None = Field(default=None, ge=1)
