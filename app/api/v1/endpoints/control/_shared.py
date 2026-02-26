"""Shared helpers for CEO Control sub-modules."""
from __future__ import annotations

from datetime import datetime

from app.core.config import PLACEHOLDER_AI_KEYS
from app.schemas.control import CloneLimitationRead

_FEEDBACK_METRICS_WINDOW_DAYS = 30


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip() or default)
        except ValueError:
            return default
    return default


def _to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip() or default)
        except ValueError:
            return default
    return default


def _append_limitation(
    limitations: list[CloneLimitationRead],
    *,
    name: str,
    severity: str,
    impact: str,
    evidence: str,
) -> None:
    limitations.append(
        CloneLimitationRead(
            name=name,
            severity=severity,
            impact=impact,
            evidence=evidence,
        )
    )


def _integration_state(
    *,
    connected: bool,
    last_sync_status: str | None,
    last_sync_at: datetime | None,
    now: datetime,
    stale_hours: int,
) -> str:
    if not connected:
        return "down"
    if last_sync_status == "error":
        return "degraded"
    if last_sync_at is None:
        return "degraded"
    age_hours = (now - last_sync_at).total_seconds() / 3600
    if age_hours >= stale_hours:
        return "stale"
    return "healthy"


def _integration_suggested_actions(
    *,
    integration_type: str,
    state: str,
    last_sync_status: str | None,
    age_hours: float | None,
    stale_hours: int,
) -> list[str]:
    actions: list[str] = []
    if state == "down":
        actions.append(f"Connect {integration_type} using /api/v1/integrations/{integration_type}/connect.")
        return actions
    if last_sync_status == "error":
        actions.append(f"Run /api/v1/integrations/{integration_type}/status and verify token/scopes.")
        actions.append(f"Replay sync via /api/v1/integrations/{integration_type}/sync.")
    if state == "stale":
        actions.append(f"Sync is stale ({age_hours or 'unknown'}h). Run /api/v1/integrations/{integration_type}/sync.")
    if state == "degraded" and last_sync_status != "error":
        actions.append("Connection exists but health is degraded; run status + sync to refresh metadata.")
    if not actions:
        actions.append(f"{integration_type} integration is healthy; keep hourly sync enabled.")
    if age_hours is not None and age_hours >= (stale_hours * 2):
        actions.append("Escalate to owner if stale over 2x SLA window.")
    return actions[:3]


def _provider_key_ready(key: str | None) -> bool:
    cleaned = (key or "").strip()
    return bool(cleaned) and cleaned not in PLACEHOLDER_AI_KEYS
