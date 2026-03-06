from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.domains.automation.models import WorkflowRunStatus

_RETRYABLE_ERROR_MARKERS = (
    "timeout",
    "temporar",
    "connection",
    "network",
    "rate limit",
    "unavailable",
    "retryable",
)


def is_retryable_error(error_summary: str | None) -> bool:
    text = str(error_summary or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _RETRYABLE_ERROR_MARKERS)


def compute_next_retry_at(*, retry_count: int, now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    exponent = max(0, int(retry_count) - 1)
    base_delay = max(0, int(settings.WORKFLOW_RETRY_BASE_SECONDS))
    max_delay = max(base_delay, int(settings.WORKFLOW_RETRY_MAX_SECONDS))
    delay_seconds = min(max_delay, base_delay * (2**exponent))
    return current + timedelta(seconds=delay_seconds)


def can_retry_run(*, run) -> bool:
    return int(run.retry_count or 0) < int(settings.WORKFLOW_RETRY_MAX_ATTEMPTS)


def should_mark_run_stuck(*, run, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if str(run.status) != WorkflowRunStatus.RUNNING:
        return False
    if run.last_heartbeat_at is None:
        return False
    timeout = timedelta(seconds=max(30, int(settings.WORKFLOW_HEARTBEAT_TIMEOUT_SECONDS)))
    return run.last_heartbeat_at < current - timeout


def should_resume_retry_wait_run(*, run, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if str(run.status) != WorkflowRunStatus.RETRY_WAIT:
        return False
    if run.next_retry_at is None:
        return True
    return run.next_retry_at <= current
