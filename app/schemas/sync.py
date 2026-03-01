"""Pydantic response model for standardised sync results."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SyncResultResponse(BaseModel):
    """API response shape returned by all integration sync endpoints."""

    provider: str
    synced: int
    skipped: int
    errors: list[str] = []
    last_sync_at: datetime
