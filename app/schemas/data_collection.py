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
    target: str
    source: str
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
