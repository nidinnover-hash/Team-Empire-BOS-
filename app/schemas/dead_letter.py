"""Dead-letter queue schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeadLetterEntryRead(BaseModel):
    id: int
    organization_id: int
    source_type: str
    source_id: str | None = None
    source_detail: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    error_type: str | None = None
    attempts: int
    max_attempts: int
    status: str
    resolved_by: int | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}


class DeadLetterListRead(BaseModel):
    generated_at: datetime
    count: int
    items: list[DeadLetterEntryRead]


class DeadLetterCountsRead(BaseModel):
    generated_at: datetime
    by_status: dict[str, int] = Field(default_factory=dict)
    by_source_type: dict[str, int] = Field(default_factory=dict)
    total_pending: int = 0
