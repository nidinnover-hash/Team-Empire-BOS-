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
