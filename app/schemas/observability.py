from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EventRead(BaseModel):
    id: int
    organization_id: int
    event_type: str
    actor_user_id: int | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    payload: dict = {}
    created_at: datetime | None = None


class SignalRead(BaseModel):
    id: int
    signal_id: str
    organization_id: int
    workspace_id: int | None = None
    actor_user_id: int | None = None
    topic: str
    category: str
    source: str
    entity_type: str | None = None
    entity_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    request_id: str | None = None
    summary_text: str | None = None
    payload: dict = {}
    metadata: dict = {}
    occurred_at: datetime | None = None
    created_at: datetime | None = None


class DecisionTimelineEventRead(BaseModel):
    topic: str
    occurred_at: datetime | None = None
    source: str
    summary_text: str | None = None
    payload: dict = {}


class DecisionTimelineItemRead(BaseModel):
    approval_id: int
    approval_type: str | None = None
    approval_status: str | None = None
    execution_id: int | None = None
    execution_status: str | None = None
    requested_at: datetime | None = None
    decided_at: datetime | None = None
    execution_started_at: datetime | None = None
    execution_finished_at: datetime | None = None
    approval_to_execution_ms: int | None = None
    stalled: bool = False
    timeline: list[DecisionTimelineEventRead] = []


class DecisionSummaryItemRead(BaseModel):
    approval_id: int
    approval_type: str | None = None
    approval_status: str | None = None
    execution_id: int | None = None
    execution_status: str | None = None
    requested_at: datetime | None = None
    decided_at: datetime | None = None
    execution_started_at: datetime | None = None
    execution_finished_at: datetime | None = None
    approval_to_execution_ms: int | None = None


class DecisionSummaryRead(BaseModel):
    days: int
    total_requests: int
    approved_count: int
    rejected_count: int
    pending_count: int
    approved_but_not_executed_count: int
    execution_failed_count: int
    median_approval_to_execution_ms: int | None = None
    recent_stalled: list[DecisionSummaryItemRead] = []
    recent_failed: list[DecisionSummaryItemRead] = []


class AiReliabilityProviderRead(BaseModel):
    provider: str
    total_calls: int
    failed_calls: int
    fallback_count: int
    error_rate: float
    fallback_rate: float
    avg_latency_ms: int


class AiReliabilityFailureRead(BaseModel):
    signal_id: str
    provider: str | None = None
    model_name: str | None = None
    error_type: str | None = None
    request_id: str | None = None
    fallback_from: str | None = None
    latency_ms: int | None = None
    occurred_at: datetime | None = None


class AiReliabilityRead(BaseModel):
    days: int
    total_calls: int
    failed_calls: int
    fallback_count: int
    success_rate: float
    error_rate: float
    fallback_rate: float
    avg_latency_ms: int | None = None
    providers: list[AiReliabilityProviderRead] = []
    recent_failures: list[AiReliabilityFailureRead] = []


class SchedulerHealthJobRead(BaseModel):
    job_name: str
    total_runs: int
    failed_runs: int
    success_rate: float
    avg_duration_ms: int
    last_status: str | None = None
    last_occurred_at: datetime | None = None


class SchedulerHealthFailureRead(BaseModel):
    signal_id: str
    job_name: str
    error: str | None = None
    duration_ms: int | None = None
    occurred_at: datetime | None = None


class SchedulerHealthRead(BaseModel):
    days: int
    total_runs: int
    failed_runs: int
    success_rate: float
    avg_duration_ms: int | None = None
    jobs: list[SchedulerHealthJobRead] = []
    recent_failures: list[SchedulerHealthFailureRead] = []


class WebhookReliabilityEndpointRead(BaseModel):
    endpoint_id: int | None = None
    total_deliveries: int
    failed_deliveries: int
    success_rate: float
    avg_duration_ms: int
    last_status: str | None = None
    last_event: str | None = None
    last_occurred_at: datetime | None = None


class WebhookReliabilityFailureRead(BaseModel):
    signal_id: str
    endpoint_id: int | None = None
    event: str | None = None
    error_message: str | None = None
    response_status_code: int | None = None
    duration_ms: int | None = None
    occurred_at: datetime | None = None


class WebhookReliabilityRead(BaseModel):
    days: int
    total_deliveries: int
    failed_deliveries: int
    success_rate: float
    avg_duration_ms: int | None = None
    endpoints: list[WebhookReliabilityEndpointRead] = []
    recent_failures: list[WebhookReliabilityFailureRead] = []


class AIProviderStatsRead(BaseModel):
    provider: str
    call_count: int
    avg_latency_ms: int
    total_input_tokens: int
    total_output_tokens: int


class ObservabilitySummaryRead(BaseModel):
    days: int
    total_ai_calls: int
    provider_stats: list[AIProviderStatsRead]
    fallback_rate: float
    error_rate: float
    total_approvals: int
    rejection_rate: float
    approval_breakdown: dict[str, int]
    runtime_stats: dict[str, int] = {}


class AICallLogRead(BaseModel):
    id: int
    provider: str
    model_name: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    used_fallback: bool
    fallback_from: str | None = None
    error_type: str | None = None
    request_id: str | None = None
    created_at: datetime | None = None


class DecisionTraceSummaryRead(BaseModel):
    id: int
    trace_type: str
    title: str
    summary: str
    confidence_score: float = 0.0
    request_id: str | None = None
    created_at: datetime | None = None


class StorageTableStatRead(BaseModel):
    table: str
    row_count: int


class StorageSummaryRead(BaseModel):
    org_id: int
    generated_at: datetime
    total_rows: int
    retention_days_chat: int
    tables: list[StorageTableStatRead]
