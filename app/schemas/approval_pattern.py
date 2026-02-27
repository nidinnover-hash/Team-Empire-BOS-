from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApprovalPatternRead(BaseModel):
    id: int
    approval_type: str
    sample_payload: dict[str, Any] = Field(default_factory=dict)
    approved_count: int = 0
    rejected_count: int = 0
    reject_count: int = 0
    is_auto_approve_enabled: bool = False
    auto_approve_threshold: float = 0.9
    confidence_score: float = 0.0


class ApprovalPatternUpdate(BaseModel):
    is_auto_approve_enabled: bool | None = None
    # threshold is the minimum number of approved decisions required before auto-approval
    # is allowed.  This is stored as a float for flexibility (e.g. partial counts),
    # but there is no upper bound; callers may set integers like 3 or 10.
    auto_approve_threshold: float | None = Field(default=None, ge=0.0)
