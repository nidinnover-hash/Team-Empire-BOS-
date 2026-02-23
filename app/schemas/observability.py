from pydantic import BaseModel


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
    model_name: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    used_fallback: bool
    fallback_from: str | None = None
    error_type: str | None = None
    request_id: str | None = None
    created_at: str | None = None


class DecisionTraceSummaryRead(BaseModel):
    id: int
    trace_type: str
    title: str
    summary: str
    confidence_score: float | None = None
    request_id: str | None = None
    created_at: str | None = None
