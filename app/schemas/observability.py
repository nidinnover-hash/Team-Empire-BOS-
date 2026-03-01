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
