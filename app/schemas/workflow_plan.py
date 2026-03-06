from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowPlanRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=4000)
    constraints: dict = Field(default_factory=dict)
    available_integrations: list[str] = Field(default_factory=list)
    workspace_id: int | None = Field(default=None, ge=1)


class WorkflowPlanDraftRead(BaseModel):
    name: str
    summary: str
    trigger_mode: str
    steps: list[dict]
    risk_level: str
    confidence: float
