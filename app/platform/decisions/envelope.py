"""Typed decision envelope — the canonical output of any BOS decision."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class DecisionOutcome(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    SUGGESTED = "suggested"
    DEFERRED = "deferred"
    ESCALATED = "escalated"


class DecisionEnvelope(BaseModel):
    """Immutable record of a single BOS decision.

    Created by ``record_decision()`` and returned to the caller so downstream
    code can branch on ``outcome`` without re-querying the database.
    """

    model_config = ConfigDict(frozen=True)

    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    decision_type: str = Field(..., min_length=1, max_length=100)
    outcome: DecisionOutcome
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="", max_length=5000)
    organization_id: int = Field(..., ge=1)
    actor_user_id: int | None = Field(default=None, ge=1)
    entity_type: str | None = Field(default=None, max_length=120)
    entity_id: str | None = Field(default=None, max_length=255)
    signal_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trace_id: int | None = Field(default=None)
