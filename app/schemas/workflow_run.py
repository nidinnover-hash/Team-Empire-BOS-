from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowRunRequest(BaseModel):
    trigger_source: str = Field(default="manual", max_length=20)
    input_json: dict = Field(default_factory=dict)
    trigger_signal_id: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, max_length=128)


class WorkflowRunListItem(BaseModel):
    id: int
    organization_id: int
    workspace_id: int | None
    workflow_definition_id: int
    workflow_version: int
    trigger_source: str
    trigger_signal_id: str | None
    status: str
    current_step_index: int
    requested_by: int
    started_by: int | None
    approval_id: int | None
    idempotency_key: str
    result_json: dict
    error_summary: str | None
    retry_count: int
    next_retry_at: datetime | None
    last_heartbeat_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowStepRunRead(BaseModel):
    id: int
    organization_id: int
    workflow_run_id: int
    step_index: int
    step_key: str
    action_type: str
    status: str
    approval_id: int | None
    execution_id: int | None
    attempt_count: int
    idempotency_key: str
    input_json: dict
    output_json: dict
    error_text: str | None
    latency_ms: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunRead(WorkflowRunListItem):
    plan_snapshot_json: dict
    input_json: dict
    context_json: dict
    step_runs: list[WorkflowStepRunRead] = Field(default_factory=list)


class WorkflowApprovalPreviewRead(BaseModel):
    workflow_definition_id: int
    workflow_status: str
    input_json: dict
    requires_publish: bool
    step_plans: list[dict]
