from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


DataSource = Literal["manual", "whatsapp", "call", "meeting", "docs"]


class DataCollectRequest(BaseModel):
    source: DataSource = Field(..., description="manual | whatsapp | call | meeting | docs")
    target: Literal["profile_memory", "daily_context", "notes"] = "notes"
    content: str = Field(..., min_length=3, max_length=6000, description="Raw content to ingest")
    split_lines: bool = Field(
        default=True,
        description="If true, each non-empty line becomes a separate item",
    )
    key: str | None = Field(default=None, max_length=100, description="Required for profile_memory target")
    category: str | None = Field(default=None, max_length=50)
    context_type: str | None = Field(default=None, max_length=50, description="priority | meeting | blocker | decision")
    related_to: str | None = Field(default=None, max_length=100)
    for_date: date | None = None


class DataCollectResult(BaseModel):
    target: Literal["profile_memory", "daily_context", "notes"]
    source: DataSource
    ingested_count: int
    created_ids: list[int]
    message: str


class CloneProTrainingRequest(BaseModel):
    source: str = Field(default="pro_training", max_length=80)
    preferred_name: str | None = Field(default=None, max_length=80)
    communication_style: str = Field(..., min_length=3, max_length=220)
    top_priorities: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Top operating priorities in order",
    )
    operating_rules: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="How clone should make decisions",
    )
    daily_focus: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="What should be pushed into daily context as priorities",
    )
    domain_notes: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Long-form domain or business notes for later retrieval",
    )


class CloneProTrainingResult(BaseModel):
    source: str
    profile_memory_written: int
    daily_context_written: int
    notes_written: int
    memory_keys: list[str]
    message: str


class MeetingCoachingRequest(BaseModel):
    source: str = Field(default="meeting_transcript", max_length=80)
    transcript: str = Field(..., min_length=40, max_length=20000)
    objective: Literal["sales", "support", "general"] = "sales"
    speaker_name: str | None = Field(default=None, max_length=80)
    consent_confirmed: bool = Field(
        default=False,
        description="Must be true. Only process conversations where consent/legal basis exists.",
    )


class MeetingCoachingResult(BaseModel):
    objective: Literal["sales", "support", "general"]
    tone_profile: str
    strengths: list[str]
    improvement_areas: list[str]
    sales_signals: dict[str, int]
    memory_keys: list[str]
    note_id: int | None = None
    message: str


class MobileCaptureAnalyzeRequest(BaseModel):
    source: str = Field(default="mobile_capture", max_length=80)
    device_type: Literal["mobile", "tablet"] = "mobile"
    capture_type: Literal["screenshot", "photo"] = "screenshot"
    content_text: str = Field(..., min_length=10, max_length=30000)
    wanted_topics: list[str] = Field(default_factory=list, max_length=20)
    unwanted_topics: list[str] = Field(default_factory=list, max_length=20)
    create_policy_drafts: bool = True


class MobileCaptureAnalyzeResult(BaseModel):
    source: str
    device_type: str
    capture_type: str
    scanned_lines: int
    wanted_count: int
    unwanted_count: int
    memory_keys: list[str]
    policy_rule_ids: list[int]
    note_id: int | None = None
    message: str


class MobileCaptureUploadAnalyzeResult(MobileCaptureAnalyzeResult):
    filename: str
    extracted_chars: int
    ocr_engine: str


# ── Photo Character Study ────────────────────────────────────────────────

class PhotoCharacterStudyResult(BaseModel):
    filename: str
    extracted_chars: int
    ocr_engine: str
    traits: list[str]
    character_summary: str
    confidence: Literal["low", "medium", "high"]
    memory_keys: list[str]
    note_id: int | None = None
    message: str


# ── Digital Threat Detection ─────────────────────────────────────────────

ThreatSeverity = Literal["info", "low", "medium", "high", "critical"]
ThreatCategory = Literal[
    "credential_leak", "injection_attempt", "rate_abuse",
    "privilege_escalation", "data_exfiltration", "suspicious_pattern",
    "config_weakness", "dependency_risk",
]


class ThreatSignalOut(BaseModel):
    id: int
    category: str
    severity: str
    title: str
    description: str
    source: str
    auto_mitigated: bool
    created_at: str


class ThreatDetectionResult(BaseModel):
    scope: str
    signals_found: int
    signals: list[ThreatSignalOut]
    severity_breakdown: dict[str, int]
    policy_drafts_created: int
    message: str


class ThreatTrainRequest(BaseModel):
    signal_ids: list[int] = Field(..., min_length=1, max_length=50)
    action: Literal["approve", "dismiss"] = "approve"


class ThreatTrainResult(BaseModel):
    processed: int
    policies_activated: int
    policies_dismissed: int
    memory_keys: list[str]
    message: str


class ThreatLayerReport(BaseModel):
    security_score: int = Field(ge=0, le=100)
    total_signals_7d: int
    severity_breakdown: dict[str, int]
    top_threats: list[ThreatSignalOut]
    active_policies: int
    auto_mitigated_count: int
    recommendations: list[str]


# ── Personal Branding Power ─────────────────────────────────────────────

class BrandingPowerReport(BaseModel):
    branding_score: int = Field(ge=0, le=100)
    content_consistency: int = Field(ge=0, le=100)
    platform_coverage: int = Field(ge=0, le=100)
    audience_alignment: int = Field(ge=0, le=100)
    total_posts_30d: int
    published_posts_30d: int
    platforms_active: list[str]
    content_themes: list[str]
    strengths: list[str]
    gaps: list[str]
    next_actions: list[str]


# ── Fraud Detection ─────────────────────────────────────────────────────

FraudCategory = Literal[
    "financial_anomaly", "identity_fraud", "duplicate_transaction",
    "unauthorized_access", "data_tampering", "invoice_fraud",
    "expense_fraud", "phantom_vendor",
]

class FraudSignalOut(BaseModel):
    category: str
    severity: str
    title: str
    description: str
    source: str
    risk_score: int = Field(ge=0, le=100)


class FraudDetectionResult(BaseModel):
    scope: str
    signals_found: int
    signals: list[FraudSignalOut]
    risk_breakdown: dict[str, int]
    total_anomalies: int
    message: str


class FraudLayerReport(BaseModel):
    fraud_risk_score: int = Field(ge=0, le=100)
    total_anomalies_30d: int
    risk_breakdown: dict[str, int]
    top_signals: list[FraudSignalOut]
    guardrails_active: int
    recommendations: list[str]


# ── AI News Digest ──────────────────────────────────────────────────────

class NewsDigestRequest(BaseModel):
    interests: list[str] = Field(
        default_factory=lambda: [
            "artificial intelligence", "AI startups", "LLM",
            "education technology", "overseas education",
            "personal branding", "SaaS", "automation",
        ],
        max_length=20,
    )
    max_items: int = Field(default=10, ge=1, le=20)


class NewsDigestItem(BaseModel):
    title: str
    summary: str
    relevance_tag: str
    relevance_score: int = Field(ge=0, le=100)


class NewsDigestResult(BaseModel):
    items: list[NewsDigestItem]
    interests_matched: list[str]
    memory_keys: list[str]
    message: str


# ── Ethical Boundary Layer ──────────────────────────────────────────────

class EthicalViolation(BaseModel):
    category: str
    severity: str
    description: str
    source: str


class EthicalBoundaryReport(BaseModel):
    ethics_score: int = Field(ge=0, le=100)
    violations_found: int
    violations: list[EthicalViolation]
    category_breakdown: dict[str, int]
    active_guardrails: int
    compliance_areas: list[str]
    recommendations: list[str]
