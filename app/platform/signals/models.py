"""Compatibility exports and small internal signal types."""

from pydantic import BaseModel, Field

from app.platform.signals.schemas import SignalCategory, SignalEnvelope


class SignalCursor(BaseModel):
    """Small query cursor used for future pagination work."""

    occurred_at: str | None = None
    signal_id: str | None = None


class SignalQueryFilters(BaseModel):
    """Explicit filters for signal lookup operations."""

    organization_id: int | None = Field(default=None, ge=1)
    topic: str | None = None
    correlation_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


__all__ = [
    "SignalCategory",
    "SignalCursor",
    "SignalEnvelope",
    "SignalQueryFilters",
]
