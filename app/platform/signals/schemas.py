"""Typed signal envelope schemas."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class SignalCategory(StrEnum):
    EXTERNAL = "external"
    DOMAIN = "domain"
    DECISION = "decision"
    EXECUTION = "execution"
    INTELLIGENCE = "intelligence"
    SYSTEM = "system"


class SignalEnvelope(BaseModel):
    """Canonical immutable signal structure used by the BOS runtime."""

    model_config = ConfigDict(frozen=True)

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str = Field(..., min_length=1, max_length=120)
    category: SignalCategory
    organization_id: int = Field(..., ge=1)
    workspace_id: int | None = Field(default=None, ge=1)
    actor_user_id: int | None = Field(default=None, ge=1)
    source: str = Field(..., min_length=1, max_length=120)
    entity_type: str | None = Field(default=None, max_length=120)
    entity_id: str | None = Field(default=None, max_length=255)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = Field(default=None, max_length=255)
    causation_id: str | None = Field(default=None, max_length=255)
    request_id: str | None = Field(default=None, max_length=255)
    summary_text: str | None = Field(default=None, max_length=1000)
    payload: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
