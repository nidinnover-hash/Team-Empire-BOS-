"""
Background sync scheduler — periodically syncs all connected integrations
and runs automation/maintenance jobs so the AI always has fresh context.

Two modes:
  1. Scheduled: runs every SYNC_INTERVAL_MINUTES (default 30) in the background.
  2. On-demand: call trigger_sync_for_org(org_id) from login / dashboard load;
     a per-org throttle prevents redundant syncs within THROTTLE_MINUTES.

Execution model:
  - Integration jobs run through a dedicated worker pool.
  - Automation/maintenance jobs run through a separate worker pool.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import LOG_DETAIL_MAX_CHARS
from app.core.resilience import IntegrationSyncError, RetryPolicy, error_details, run_with_retry
from app.db.session import AsyncSessionLocal
from app.jobs._helpers import record_job_run, scheduler_error_category
from app.jobs.approval_jobs import auto_reject_expired_approvals
from app.jobs.infra import maybe_run_daily_backup, retry_webhook_deliveries
from app.jobs.intelligence import (
    _collect_stale_integrations as _jobs_collect_stale_integrations,
)
from app.jobs.intelligence import (
    _extract_top_risks as _jobs_extract_top_risks,
)
from app.jobs.intelligence import (
    _format_briefing_summary as _jobs_format_briefing_summary,
)
from app.jobs.intelligence import (
    _format_ceo_risk_digest as _jobs_format_ceo_risk_digest,
)
from app.jobs.intelligence import (
    _last_ceo_summary_date_by_org as _jobs_last_ceo_summary_date_by_org,
)
from app.jobs.intelligence import (
    _last_empire_flow_digest_date_by_org as _jobs_last_empire_flow_digest_date_by_org,
)
from app.jobs.intelligence import (
    _last_pending_digest_date_by_org as _jobs_last_pending_digest_date_by_org,
)
from app.jobs.intelligence import (
    _maybe_send_daily_ceo_slack_summary as _jobs_maybe_send_daily_ceo_slack_summary,
)
from app.jobs.intelligence import (
    _severity_rank as _jobs_severity_rank,
)
from app.jobs.intelligence import (
    check_morning_briefing,
    maybe_emit_daily_briefing_notification,
    maybe_generate_daily_ceo_summary,
    maybe_generate_daily_empire_flow_digest,
    maybe_generate_daily_pending_digest,
    maybe_run_knowledge_consolidation,
    maybe_run_weekly_coaching,
)
from app.jobs.maintenance import (
    cleanup_old_chat_messages,
    cleanup_old_job_runs_and_snapshots,
    cleanup_old_logs,
    cleanup_old_trend_events,
)
from app.jobs.monitoring import (
    _last_scheduler_slo_alert_key_by_org as _jobs_last_scheduler_slo_alert_key_by_org,
)
from app.jobs.monitoring import (
    check_follow_up_contacts,
    check_goal_deadlines,
    check_stale_tasks,
    check_token_health_job,
    monitor_scheduler_slos,
)
from app.jobs.social_jobs import publish_due_social_posts
from app.jobs.telemetry_jobs import snapshot_layer_scores_job, snapshot_org_trends_job

# Backward-compatible aliases so existing code and tests keep working
_auto_reject_expired_approvals = auto_reject_expired_approvals
_cleanup_old_chat_messages = cleanup_old_chat_messages
_cleanup_old_logs = cleanup_old_logs
_cleanup_old_job_runs_and_snapshots = cleanup_old_job_runs_and_snapshots
_cleanup_old_trend_events = cleanup_old_trend_events
_check_morning_briefing = check_morning_briefing
_maybe_generate_daily_ceo_summary = maybe_generate_daily_ceo_summary
_maybe_generate_daily_pending_digest = maybe_generate_daily_pending_digest
_maybe_generate_daily_empire_flow_digest = maybe_generate_daily_empire_flow_digest
_publish_due_social_posts = publish_due_social_posts
_check_goal_deadlines = check_goal_deadlines
_check_stale_tasks = check_stale_tasks
_maybe_emit_daily_briefing_notification = maybe_emit_daily_briefing_notification
_maybe_run_knowledge_consolidation = maybe_run_knowledge_consolidation
_maybe_run_weekly_coaching = maybe_run_weekly_coaching
_check_follow_up_contacts = check_follow_up_contacts
_check_token_health_job = check_token_health_job
_snapshot_org_trends_job = snapshot_org_trends_job
_snapshot_layer_scores_job = snapshot_layer_scores_job
_maybe_run_daily_backup = maybe_run_daily_backup
_retry_webhook_deliveries = retry_webhook_deliveries
_monitor_scheduler_slos = monitor_scheduler_slos
_record_job_run = record_job_run


async def _run_alert_engine(db: AsyncSession, org_id: int) -> dict:
    """Run proactive alert checks for an organization."""
    from app.services.alert_engine import run_alert_checks
    return await run_alert_checks(db, org_id)
_scheduler_error_category = scheduler_error_category
_collect_stale_integrations = _jobs_collect_stale_integrations
_extract_top_risks = _jobs_extract_top_risks
_format_briefing_summary = _jobs_format_briefing_summary
_format_ceo_risk_digest = _jobs_format_ceo_risk_digest
_maybe_send_daily_ceo_slack_summary = _jobs_maybe_send_daily_ceo_slack_summary
_severity_rank = _jobs_severity_rank

logger = logging.getLogger(__name__)
_SYNC_RETRY_POLICY = RetryPolicy(
    attempts=2,
    timeout_seconds=30.0,
    backoff_seconds=1.0,
    retry_exceptions=(IntegrationSyncError, TimeoutError, ConnectionError),
)

# Per-org throttle: don't fire on-demand sync more than once per N minutes.
# Default 15 — overridden by settings.SYNC_THROTTLE_MINUTES at runtime.
_last_synced: dict[int, datetime] = {}
_sync_locks: dict[int, asyncio.Lock] = {}  # prevent concurrent syncs for the same org
_sync_failure_streak: dict[tuple[int, str], int] = {}
# Circuit breaker: after N consecutive failures, pause sync for a cooldown period.
_circuit_open_until: dict[tuple[int, str], datetime] = {}
_CIRCUIT_BREAKER_COOLDOWN_MINUTES = 60
# Lightweight retry/backoff telemetry for reliability monitoring.
_scheduler_retry_telemetry: dict[str, object] = {
    "operations_total": 0,
    "operations_succeeded": 0,
    "operations_failed": 0,
    "retries_total": 0,
    "backoff_seconds_total": 0.0,
    "last_error_type": None,
    "last_error_at": None,
    "per_integration": {},
}
# Per-org daily dedup state (canonical copies live in app/jobs/ modules; aliased here for compat)
_last_ceo_summary_date_by_org = _jobs_last_ceo_summary_date_by_org
_last_empire_flow_digest_date_by_org = _jobs_last_empire_flow_digest_date_by_org
_last_pending_digest_date_by_org = _jobs_last_pending_digest_date_by_org
_last_scheduler_slo_alert_key_by_org = _jobs_last_scheduler_slo_alert_key_by_org


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _coerce_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def get_last_synced_for_org(org_id: int) -> datetime | None:
    """Return the last sync timestamp for an org, or None if never synced."""
    return _last_synced.get(org_id)


def _estimated_backoff_seconds(retries: int) -> float:
    if retries <= 0:
        return 0.0
    base = max(0.0, float(_SYNC_RETRY_POLICY.backoff_seconds))
    return float(sum(base * (2**idx) for idx in range(retries)))


def _record_retry_telemetry(
    *,
    org_id: int,
    integration: str,
    attempts: int,
    ok: bool,
    error_type: str | None = None,
) -> None:
    retries = max(0, attempts - 1)
    backoff_seconds = _estimated_backoff_seconds(retries)
    per_integration = _scheduler_retry_telemetry.setdefault("per_integration", {})
    if not isinstance(per_integration, dict):
        per_integration = {}
        _scheduler_retry_telemetry["per_integration"] = per_integration

    key = f"{org_id}:{integration}"
    bucket = per_integration.get(key)
    if not isinstance(bucket, dict):
        bucket = {
            "operations_total": 0,
            "operations_succeeded": 0,
            "operations_failed": 0,
            "retries_total": 0,
            "backoff_seconds_total": 0.0,
            "last_error_type": None,
            "last_error_at": None,
        }
        per_integration[key] = bucket

    _scheduler_retry_telemetry["operations_total"] = (
        _coerce_int(_scheduler_retry_telemetry.get("operations_total")) + 1
    )
    _scheduler_retry_telemetry["retries_total"] = (
        _coerce_int(_scheduler_retry_telemetry.get("retries_total")) + retries
    )
    _scheduler_retry_telemetry["backoff_seconds_total"] = (
        _coerce_float(_scheduler_retry_telemetry.get("backoff_seconds_total")) + backoff_seconds
    )
    bucket["operations_total"] = int(bucket["operations_total"]) + 1
    bucket["retries_total"] = int(bucket["retries_total"]) + retries
    bucket["backoff_seconds_total"] = float(bucket["backoff_seconds_total"]) + backoff_seconds

    if ok:
        _scheduler_retry_telemetry["operations_succeeded"] = (
            _coerce_int(_scheduler_retry_telemetry.get("operations_succeeded")) + 1
        )
        bucket["operations_succeeded"] = int(bucket["operations_succeeded"]) + 1
    else:
        now_iso = datetime.now(UTC).isoformat()
        _scheduler_retry_telemetry["operations_failed"] = (
            _coerce_int(_scheduler_retry_telemetry.get("operations_failed")) + 1
        )
        _scheduler_retry_telemetry["last_error_type"] = error_type
        _scheduler_retry_telemetry["last_error_at"] = now_iso
        bucket["operations_failed"] = int(bucket["operations_failed"]) + 1
        bucket["last_error_type"] = error_type
        bucket["last_error_at"] = now_iso


def get_scheduler_retry_telemetry() -> dict[str, object]:
    """Expose scheduler retry/backoff counters for health dashboards."""
    per_integration_raw = _scheduler_retry_telemetry.get("per_integration", {})
    per_integration = per_integration_raw if isinstance(per_integration_raw, dict) else {}
    return {
        "operations_total": _coerce_int(_scheduler_retry_telemetry.get("operations_total")),
        "operations_succeeded": _coerce_int(_scheduler_retry_telemetry.get("operations_succeeded")),
        "operations_failed": _coerce_int(_scheduler_retry_telemetry.get("operations_failed")),
        "retries_total": _coerce_int(_scheduler_retry_telemetry.get("retries_total")),
        "backoff_seconds_total": _coerce_float(_scheduler_retry_telemetry.get("backoff_seconds_total")),
        "last_error_type": _scheduler_retry_telemetry.get("last_error_type"),
        "last_error_at": _scheduler_retry_telemetry.get("last_error_at"),
        "per_integration": {
            str(key): dict(value) for key, value in per_integration.items() if isinstance(value, dict)
        },
    }


def _throttle_minutes() -> int:
    try:
        from app.core.config import settings
        value = int(settings.SYNC_THROTTLE_MINUTES)
        return max(value, 0)
    except (ImportError, AttributeError, TypeError, ValueError):
        return 15


# Background task handle (stored so we can cancel on shutdown)
_scheduler_task: asyncio.Task | None = None
_inflight_tasks: set[asyncio.Task] = set()
_MAX_SCHEDULER_POOL_SIZE = 64


def _task_error_handler(task: asyncio.Task) -> None:
    """Log unhandled exceptions from fire-and-forget tasks."""
    _inflight_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Background task failed: %s: %s", type(exc).__name__, exc)


def _clamp_pool_size(raw_value: object, *, default: int) -> int:
    try:
        value = int(raw_value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(1, min(value, _MAX_SCHEDULER_POOL_SIZE))


def _integration_pool_size() -> int:
    from app.core.config import settings

    return _clamp_pool_size(
        getattr(settings, "SYNC_INTEGRATION_WORKERS", 4),
        default=4,
    )


def _automation_pool_size() -> int:
    from app.core.config import settings

    return _clamp_pool_size(
        getattr(settings, "SYNC_AUTOMATION_WORKERS", 4),
        default=4,
    )


# Helper functions (_severity_rank, _extract_top_risks, _format_ceo_risk_digest,
# _collect_stale_integrations, _record_job_run, _maybe_send_daily_ceo_slack_summary)
# extracted to app/jobs/intelligence.py and app/jobs/_helpers.py.
# Backward-compatible aliases are defined above.


# ── Core sync runner ──────────────────────────────────────────────────────────

async def _run_integrations(db: AsyncSession, org_id: int) -> None:
    """Sync all connected integrations for org_id. Logs but never raises."""
    from sqlalchemy import update

    from app.core.config import settings
    from app.models.integration import Integration
    from app.services import (
        calendly_service,
        clickup_service,
        compliance_engine,
        do_service,
        email_control,
        email_service,
        github_service,
        google_analytics_service,
        hubspot_service,
        notion_service,
        slack_service,
        stripe_service,
    )
    from app.services.calendar_service import sync_calendar_events
    failure_alert_threshold = max(1, int(getattr(settings, "SYNC_FAILURE_ALERT_THRESHOLD", 3)))
    async def _mark_status(int_type: str, status: str) -> None:
        try:
            values: dict = {"last_sync_status": status}
            if status == "ok":
                values["sync_error_count"] = 0
            else:
                # Increment persistent error counter so circuit-breaker survives restarts
                values["sync_error_count"] = Integration.sync_error_count + 1
            await db.execute(
                update(Integration)
                .where(Integration.organization_id == org_id, Integration.type == int_type)
                .values(**values)
            )
        except (SQLAlchemyError, AttributeError) as exc:
            logger.debug(
                "Status update failed org=%d integration=%s status=%s: %s",
                org_id,
                int_type,
                status,
                type(exc).__name__,
            )

    async def _run_sync_operation(name: str, fn: Any) -> dict[str, object]:
        result = await fn(db, org_id)
        if isinstance(result, dict) and result.get("error"):
            raise IntegrationSyncError(
                provider=name,
                code="sync_error",
                message=str(result.get("error")),
                retryable=True,
            )
        return result if isinstance(result, dict) else {"ok": True}

    for name, fn in [
        ("clickup", clickup_service.sync_clickup_tasks),
        ("github", github_service.sync_github),
        ("digitalocean", do_service.sync_digitalocean),
        ("slack", slack_service.sync_slack_messages),
        ("notion", notion_service.sync_pages_to_notes),
        ("calendly", calendly_service.sync_events),
        ("google_analytics", google_analytics_service.sync_analytics),
        ("stripe", stripe_service.sync_stripe_data),
        ("hubspot", hubspot_service.sync_hubspot_data),
    ]:
        # Circuit breaker: skip integration if in cooldown after repeated failures
        cb_key = (org_id, name)
        cb_until = _circuit_open_until.get(cb_key)
        if cb_until and datetime.now(UTC) < cb_until:
            logger.info("Circuit breaker open for %s org=%d until %s, skipping", name, org_id, cb_until.isoformat())
            continue

        started = datetime.now(UTC)
        attempts_made = 0
        try:
            async def _op(_name: str = name, _fn: Any = fn) -> dict[str, object]:
                nonlocal attempts_made
                attempts_made += 1
                return await _run_sync_operation(_name, _fn)

            result = await run_with_retry(
                _op,
                attempts=_SYNC_RETRY_POLICY.attempts,
                timeout_seconds=_SYNC_RETRY_POLICY.timeout_seconds,
                backoff_seconds=_SYNC_RETRY_POLICY.backoff_seconds,
                retry_exceptions=_SYNC_RETRY_POLICY.retry_exceptions,
            )
            logger.debug("Sync %s org=%d -> %s", name, org_id, result)
            _sync_failure_streak[(org_id, name)] = 0
            _circuit_open_until.pop((org_id, name), None)  # close circuit breaker
            _record_retry_telemetry(
                org_id=org_id,
                integration=name,
                attempts=max(1, attempts_made),
                ok=True,
            )
            await _mark_status(name, "ok")
            await _record_job_run(
                db,
                org_id=org_id,
                job_name=f"{name}_sync",
                status="ok",
                started_at=started,
                finished_at=datetime.now(UTC),
                details={"result": result if isinstance(result, dict) else {"ok": True}},
            )
        except asyncio.CancelledError:
            raise
        except (
            SQLAlchemyError,
            IntegrationSyncError,
            TimeoutError,
            ConnectionError,
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
            ImportError,
            AttributeError,
        ) as exc:
            key = (org_id, name)
            current = _sync_failure_streak.get(key, 0) + 1
            _sync_failure_streak[key] = current
            _record_retry_telemetry(
                org_id=org_id,
                integration=name,
                attempts=max(1, attempts_made),
                ok=False,
                error_type=type(exc).__name__,
            )
            logger.warning("Background %s sync failed org=%d: %s: %s", name, org_id, type(exc).__name__, str(exc)[:LOG_DETAIL_MAX_CHARS])
            if current >= failure_alert_threshold:
                cooldown = timedelta(minutes=_CIRCUIT_BREAKER_COOLDOWN_MINUTES)
                _circuit_open_until[key] = datetime.now(UTC) + cooldown
                logger.error(
                    "Circuit breaker opened for %s org=%d (streak=%d, cooldown=%dmin)",
                    name,
                    org_id,
                    current,
                    _CIRCUIT_BREAKER_COOLDOWN_MINUTES,
                )
                try:
                    from app.services.notification import create_notification
                    await create_notification(
                        db,
                        organization_id=org_id,
                        type="integration_error",
                        severity="warning",
                        title=f"{name} sync circuit breaker activated",
                        message=f"{name} failed {current} times. Paused for {_CIRCUIT_BREAKER_COOLDOWN_MINUTES}min.",
                        source="sync_scheduler",
                        entity_type="integration",
                    )
                except Exception:
                    logger.warning("Failed to create circuit breaker notification for %s org=%d", name, org_id)
            await _mark_status(name, "error")
            details = error_details(exc)
            await _record_job_run(
                db,
                org_id=org_id,
                job_name=f"{name}_sync",
                status="error",
                started_at=started,
                finished_at=datetime.now(UTC),
                details=details,
                error=f"{type(exc).__name__}: {str(exc)[:LOG_DETAIL_MAX_CHARS]}",
            )

    # Resolve the org's admin/CEO user for audit attribution instead of
    # hardcoding user-id 1.  Falls back to None (scheduler context) if no
    # admin user exists or DB is unavailable.
    _actor_uid: int | None = None
    try:
        from app.models.user import User
        _admin_result = await db.execute(
            select(User).where(
                User.organization_id == org_id,
                User.role.in_(["CEO", "ADMIN"]),
                User.is_active.is_(True),
            ).order_by(User.id).limit(1)
        )
        _admin_user = _admin_result.scalar_one_or_none()
        _actor_uid = int(_admin_user.id) if _admin_user else None
    except (SQLAlchemyError, AttributeError, TypeError, ValueError):
        logger.debug("Could not resolve admin user for org=%d, using actor_uid=None", org_id)

    # Email sync + control classification loop (best effort)
    started = datetime.now(UTC)
    try:
        if getattr(settings, "FEATURE_EMAIL_SYNC", True):
            # Circuit breaker check for email
            email_cb_key = (org_id, "email")
            email_cb_until = _circuit_open_until.get(email_cb_key)
            if email_cb_until and datetime.now(UTC) < email_cb_until:
                logger.info("Circuit breaker open for email org=%d until %s, skipping", org_id, email_cb_until.isoformat())
            else:
                try:
                    async def _email_sync_op() -> dict[str, object]:
                        await email_service.sync_emails(db, org_id=org_id, actor_user_id=_actor_uid)  # type: ignore[arg-type]
                        return {"ok": True}

                    await run_with_retry(
                        _email_sync_op,
                        attempts=_SYNC_RETRY_POLICY.attempts,
                        timeout_seconds=_SYNC_RETRY_POLICY.timeout_seconds,
                        backoff_seconds=_SYNC_RETRY_POLICY.backoff_seconds,
                        retry_exceptions=_SYNC_RETRY_POLICY.retry_exceptions,
                    )
                    _sync_failure_streak[email_cb_key] = 0
                    _circuit_open_until.pop(email_cb_key, None)
                except asyncio.CancelledError:
                    raise
                except (
                    SQLAlchemyError,
                    IntegrationSyncError,
                    TimeoutError,
                    ConnectionError,
                    RuntimeError,
                    ValueError,
                    TypeError,
                    OSError,
                    ImportError,
                    AttributeError,
                ) as exc:
                    email_streak = _sync_failure_streak.get(email_cb_key, 0) + 1
                    _sync_failure_streak[email_cb_key] = email_streak
                    if email_streak >= failure_alert_threshold:
                        _circuit_open_until[email_cb_key] = datetime.now(UTC) + timedelta(minutes=_CIRCUIT_BREAKER_COOLDOWN_MINUTES)
                    logger.warning(
                        "Email sync failed org=%d: %s: %s",
                        org_id,
                        type(exc).__name__,
                        str(exc)[:300],
                    )
            control_result = await email_control.process_inbox_controls(
                db,
                org_id=org_id,
                actor_user_id=_actor_uid,  # type: ignore[arg-type]
                limit=100,
            )
            processed = control_result.get("processed", 0)
            tasks_created = control_result.get("tasks_created", 0)
            approvals_created = control_result.get("approvals_created", 0)
            await _record_job_run(
                db,
                org_id=org_id,
                job_name="email_control_loop",
                status="ok",
                started_at=started,
                finished_at=datetime.now(UTC),
                details={
                    "processed": processed if isinstance(processed, int) else 0,
                    "tasks_created": tasks_created if isinstance(tasks_created, int) else 0,
                    "approvals_created": approvals_created if isinstance(approvals_created, int) else 0,
                },
            )
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError,
        IntegrationSyncError,
        TimeoutError,
        ConnectionError,
        RuntimeError,
        ValueError,
        TypeError,
        OSError,
        ImportError,
        AttributeError,
    ) as exc:
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="email_control_loop",
            status="error",
            started_at=started,
            finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:LOG_DETAIL_MAX_CHARS]}",
        )

    # Google Calendar sync - stored as DailyContext, auto-included in memory
    started = datetime.now(UTC)
    try:
        result = await run_with_retry(
            lambda: sync_calendar_events(db, organization_id=org_id),
            attempts=_SYNC_RETRY_POLICY.attempts,
            timeout_seconds=_SYNC_RETRY_POLICY.timeout_seconds,
            backoff_seconds=_SYNC_RETRY_POLICY.backoff_seconds,
            retry_exceptions=_SYNC_RETRY_POLICY.retry_exceptions,
        )
        logger.debug("Sync calendar org=%d -> %s", org_id, result)
        await _mark_status("google_calendar", "ok")
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="google_calendar_sync",
            status="ok",
            started_at=started,
            finished_at=datetime.now(UTC),
            details={"result": result if isinstance(result, dict) else {"ok": True}},
        )
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError,
        IntegrationSyncError,
        TimeoutError,
        ConnectionError,
        RuntimeError,
        ValueError,
        TypeError,
        OSError,
        ImportError,
        AttributeError,
    ) as exc:
        logger.warning("Background calendar sync failed org=%d: %s: %s", org_id, type(exc).__name__, str(exc)[:LOG_DETAIL_MAX_CHARS])
        await _mark_status("google_calendar", "error")
        details = error_details(exc)
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="google_calendar_sync",
            status="error",
            started_at=started,
            finished_at=datetime.now(UTC),
            details=details,
            error=f"{type(exc).__name__}: {str(exc)[:LOG_DETAIL_MAX_CHARS]}",
        )

    started = datetime.now(UTC)
    try:
        # Suggest-only compliance scan: records violations, blocks nothing.
        report = await compliance_engine.run_compliance(db, org_id)
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="compliance_run",
            status="ok",
            started_at=started,
            finished_at=datetime.now(UTC),
            details={"compliance_score": report.get("compliance_score")},
        )
        if hasattr(db, "commit"):
            await db.commit()
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError,
        IntegrationSyncError,
        TimeoutError,
        ConnectionError,
        RuntimeError,
        ValueError,
        TypeError,
        OSError,
        ImportError,
        AttributeError,
    ) as exc:
        details = error_details(exc)
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="compliance_run",
            status="error",
            started_at=started,
            finished_at=datetime.now(UTC),
            details=details,
            error=f"{type(exc).__name__}: {str(exc)[:LOG_DETAIL_MAX_CHARS]}",
        )
        if hasattr(db, "commit"):
            await db.commit()


async def replay_job_for_org(db: AsyncSession, org_id: int, job_name: str) -> dict[str, object]:
    """Manually replay a scheduler job for one organization."""
    from app.services import (
        clickup_service,
        compliance_engine,
        do_service,
        github_service,
        slack_service,
    )
    from app.services.calendar_service import sync_calendar_events

    started = datetime.now(UTC)
    try:
        if job_name == "clickup_sync":
            result = await clickup_service.sync_clickup_tasks(db, org_id)
        elif job_name == "github_sync":
            result = await github_service.sync_github(db, org_id)
        elif job_name == "digitalocean_sync":
            result = await do_service.sync_digitalocean(db, org_id)
        elif job_name == "slack_sync":
            result = await slack_service.sync_slack_messages(db, org_id)
        elif job_name == "google_calendar_sync":
            result = await sync_calendar_events(db, organization_id=org_id)
        elif job_name == "compliance_run":
            result = await compliance_engine.run_compliance(db, org_id)
        elif job_name == "daily_ceo_summary":
            await _maybe_generate_daily_ceo_summary(db, org_id)
            result = {"ok": True}
        elif job_name == "social_publish_queue":
            await _publish_due_social_posts(db, org_id)
            result = {"ok": True}
        elif job_name == "cleanup_snapshots":
            await _cleanup_old_job_runs_and_snapshots(db, org_id)
            result = {"ok": True}
        elif job_name == "goal_deadline_check":
            await _check_goal_deadlines(db, org_id)
            result = {"ok": True}
        elif job_name == "stale_task_check":
            await _check_stale_tasks(db, org_id)
            result = {"ok": True}
        elif job_name == "contact_follow_up_check":
            await _check_follow_up_contacts(db, org_id)
            result = {"ok": True}
        elif job_name == "daily_briefing_notification":
            await _maybe_emit_daily_briefing_notification(db, org_id)
            result = {"ok": True}
        elif job_name == "daily_empire_flow_digest":
            await _maybe_generate_daily_empire_flow_digest(db, org_id)
            result = {"ok": True}
        elif job_name == "knowledge_consolidation":
            await _maybe_run_knowledge_consolidation(db, org_id)
            result = {"ok": True}
        elif job_name == "weekly_coaching":
            await _maybe_run_weekly_coaching(db, org_id)
            result = {"ok": True}
        elif job_name == "full_sync":
            await _run_integrations(db, org_id)
            result = {"ok": True}
        elif job_name == "cleanup_trend_events":
            await _cleanup_old_trend_events(db, org_id)
            result = {"ok": True}
        else:
            raise ValueError(f"Unsupported job_name: {job_name}")

        await _record_job_run(
            db,
            org_id=org_id,
            job_name=f"manual_{job_name}",
            status="ok",
            started_at=started,
            finished_at=datetime.now(UTC),
            details={"result": result if isinstance(result, dict) else {"ok": True}},
        )
        await db.commit()
        return {"ok": True, "job_name": job_name, "result": result}
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError,
        IntegrationSyncError,
        TimeoutError,
        ConnectionError,
        RuntimeError,
        ValueError,
        TypeError,
        OSError,
        ImportError,
        AttributeError,
    ) as exc:
        await _record_job_run(
            db,
            org_id=org_id,
            job_name=f"manual_{job_name}",
            status="error",
            started_at=started,
            finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:LOG_DETAIL_MAX_CHARS]}",
        )
        await db.commit()
        return {"ok": False, "job_name": job_name, "error": f"{type(exc).__name__}: {str(exc)[:LOG_DETAIL_MAX_CHARS]}"}

async def trigger_sync_for_org(org_id: int) -> None:
    """
    Fire-and-forget sync for a single org.
    Skips silently if the same org was synced within THROTTLE_MINUTES.
    Safe to call from login/dashboard without awaiting.
    """
    now = datetime.now(UTC)
    last = _last_synced.get(org_id)
    if last and (now - last).total_seconds() < _throttle_minutes() * 60:
        logger.debug("Sync throttled for org=%d (last=%s)", org_id, last.isoformat())
        return

    _MAX_INFLIGHT = 50
    if len(_inflight_tasks) >= _MAX_INFLIGHT:
        logger.warning("Inflight task cap reached (%d), skipping sync for org=%d", _MAX_INFLIGHT, org_id)
        return

    _last_synced[org_id] = now

    # Per-org lock prevents concurrent syncs for the same org
    lock = _sync_locks.setdefault(org_id, asyncio.Lock())

    async def _do():
        if lock.locked():
            logger.debug("Sync already running for org=%d, skipping", org_id)
            return
        async with lock:
            try:
                async with AsyncSessionLocal() as db:
                    await _run_integrations(db, org_id)
            except asyncio.CancelledError:
                raise
            except (
                SQLAlchemyError,
                IntegrationSyncError,
                TimeoutError,
                ConnectionError,
                RuntimeError,
                ValueError,
                TypeError,
                OSError,
                ImportError,
                AttributeError,
            ) as exc:
                logger.error("On-demand sync error org=%d: %s", org_id, exc)

    task = asyncio.create_task(_do())
    _inflight_tasks.add(task)
    task.add_done_callback(_task_error_handler)


# ── Periodic scheduler loop ───────────────────────────────────────────────────
# Job implementations extracted to app/jobs/ modules.
# Backward-compatible aliases are defined above near imports.



async def _run_automation_jobs_for_org(db: AsyncSession, org_id: int) -> None:
    """
    Run non-integration scheduler jobs for one org.
    Each job is isolated so one failure does not skip the rest.
    """
    from app.core.config import settings

    jobs: list[tuple[str, Any]] = [
        ("token_health_check", _check_token_health_job),
        ("goal_deadline_check", _check_goal_deadlines),
        ("stale_task_check", _check_stale_tasks),
        ("contact_follow_up_check", _check_follow_up_contacts),
        ("daily_briefing_notification", _maybe_emit_daily_briefing_notification),
        ("morning_briefing", _check_morning_briefing),
        ("daily_ceo_summary", _maybe_generate_daily_ceo_summary),
        ("daily_pending_digest", _maybe_generate_daily_pending_digest),
        ("daily_empire_flow_digest", _maybe_generate_daily_empire_flow_digest),
        ("social_publish_queue", _publish_due_social_posts),
        ("cleanup_chat_messages", _cleanup_old_chat_messages),
        ("cleanup_logs", _cleanup_old_logs),
        ("cleanup_snapshots", _cleanup_old_job_runs_and_snapshots),
        ("approval_auto_reject", _auto_reject_expired_approvals),
        ("trend_snapshot", _snapshot_org_trends_job),
        ("cleanup_trend_events", _cleanup_old_trend_events),
        ("layer_snapshot", _snapshot_layer_scores_job),
        ("knowledge_consolidation", _maybe_run_knowledge_consolidation),
        ("weekly_coaching", _maybe_run_weekly_coaching),
        ("monitor_scheduler_slo", _monitor_scheduler_slos),
        ("alert_engine", _run_alert_engine),
    ]
    if getattr(settings, "FEATURE_WORKFLOW_RELIABILITY", False):
        from app.engines.execution.workflow_recovery import recover_workflow_runs_for_org

        async def _workflow_recovery_job(job_db: AsyncSession, workflow_org_id: int) -> dict[str, int]:
            return await recover_workflow_runs_for_org(
                job_db,
                organization_id=workflow_org_id,
            )

        jobs.append(("workflow_recovery", _workflow_recovery_job))

    if getattr(settings, "FEATURE_WORKFLOW_V2", False):
        from app.services.automation_scheduler import run_due_scheduled_workflows

        async def _scheduled_workflows_job(_job_db: AsyncSession, sched_org_id: int) -> int:
            return await run_due_scheduled_workflows(sched_org_id)

        jobs.append(("scheduled_workflows", _scheduled_workflows_job))
    for job_name, job_fn in jobs:
        try:
            await job_fn(db, org_id)
        except asyncio.CancelledError:
            raise
        except (
            SQLAlchemyError,
            IntegrationSyncError,
            TimeoutError,
            ConnectionError,
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
            ImportError,
            AttributeError,
        ) as exc:
            logger.warning(
                "Automation job failed org=%d job=%s category=%s error_type=%s",
                org_id,
                job_name,
                _scheduler_error_category(exc),
                type(exc).__name__,
            )
            try:
                from app.platform.dead_letter.store import capture_failure
                await capture_failure(
                    db,
                    organization_id=org_id,
                    source_type="scheduler",
                    source_id=job_name,
                    source_detail=f"automation_job:{job_name}",
                    payload={"job_name": job_name, "org_id": org_id},
                    error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                    error_type=type(exc).__name__,
                )
            except Exception:
                logger.debug("Dead-letter capture failed for scheduler job %s", job_name, exc_info=True)


async def _run_org_pool(
    *,
    org_ids: list[int],
    worker_count: int,
    pool_name: str,
    org_runner: Any,
) -> None:
    """Run an org-scoped scheduler runner concurrently with a bounded worker pool."""
    if not org_ids:
        return
    queue: asyncio.Queue[int] = asyncio.Queue()
    for org_id in org_ids:
        queue.put_nowait(org_id)

    async def _worker(worker_index: int) -> None:
        while True:
            try:
                org_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                async with AsyncSessionLocal() as db:
                    await org_runner(db, org_id)
            except asyncio.CancelledError:
                raise
            except (
                SQLAlchemyError,
                IntegrationSyncError,
                TimeoutError,
                ConnectionError,
                RuntimeError,
                ValueError,
                TypeError,
                OSError,
                ImportError,
                AttributeError,
            ) as exc:
                logger.warning(
                    "Scheduler pool=%s worker=%d org=%d failed category=%s error_type=%s",
                    pool_name,
                    worker_index,
                    org_id,
                    _scheduler_error_category(exc),
                    type(exc).__name__,
                )
            finally:
                queue.task_done()

    effective_workers = max(1, min(worker_count, len(org_ids)))
    tasks = [
        asyncio.create_task(_worker(idx + 1))
        for idx in range(effective_workers)
    ]
    try:
        await queue.join()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _scheduler_loop(interval_minutes: int) -> None:
    """Runs forever; wakes up every interval_minutes and syncs all orgs."""
    from app.services.organization import list_organizations

    logger.info(
        "Sync scheduler started (interval=%d min, integration_workers=%d, automation_workers=%d)",
        interval_minutes,
        _integration_pool_size(),
        _automation_pool_size(),
    )
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            async with AsyncSessionLocal() as db:
                orgs = await list_organizations(db)
            org_ids = [int(org.id) for org in orgs]
            integration_workers = _integration_pool_size()
            automation_workers = _automation_pool_size()
            # _cleanup_old_chat_messages runs inside _run_automation_jobs_for_org.

            async def _integrations_runner(db: AsyncSession, org_id: int) -> None:
                await _run_integrations(db, org_id)
                _last_synced[org_id] = datetime.now(UTC)

            await asyncio.gather(
                _run_org_pool(
                    org_ids=org_ids,
                    worker_count=integration_workers,
                    pool_name="integrations",
                    org_runner=_integrations_runner,
                ),
                _run_org_pool(
                    org_ids=org_ids,
                    worker_count=automation_workers,
                    pool_name="automation",
                    org_runner=_run_automation_jobs_for_org,
                ),
            )
            async with AsyncSessionLocal() as db:
                await _retry_webhook_deliveries(db)
            # Daily database backup (once per day)
            await _maybe_run_daily_backup()
            logger.info("Scheduled sync complete (%d org(s))", len(orgs))
        except asyncio.CancelledError:
            raise
        except (
            SQLAlchemyError,
            IntegrationSyncError,
            TimeoutError,
            ConnectionError,
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
            ImportError,
            AttributeError,
        ) as exc:
            logger.error("Scheduled sync loop error: %s", exc)


def start_scheduler(interval_minutes: int = 30) -> asyncio.Task:
    """
    Create and return the background asyncio task.
    Call once from the FastAPI lifespan context manager.
    """
    global _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop(interval_minutes))
    _scheduler_task.add_done_callback(_task_error_handler)
    return _scheduler_task


async def stop_scheduler() -> None:
    """Cancel the scheduler and await in-flight sync tasks on shutdown."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            logger.debug("Scheduler task cancelled cleanly")
        _scheduler_task = None

    # Wait for any in-flight on-demand syncs to finish
    if _inflight_tasks:
        from app.core.config import settings

        grace = settings.SHUTDOWN_GRACE_SECONDS
        current_loop = asyncio.get_running_loop()
        alive = {t for t in _inflight_tasks if not t.done()}
        if not alive:
            _inflight_tasks.clear()
            return

        # Tasks can belong to different loops across tests; only await same-loop tasks.
        same_loop_alive = {t for t in alive if t.get_loop() is current_loop}
        foreign_loop_alive = alive - same_loop_alive

        for task in foreign_loop_alive:
            try:
                task.cancel()
            except RuntimeError:
                logger.debug("Foreign-loop task cancellation skipped due to closing event loop")

        if not same_loop_alive:
            _inflight_tasks.clear()
            return

        logger.info("Awaiting %d in-flight sync tasks (grace=%ds)...", len(same_loop_alive), grace)
        _done, pending = await asyncio.wait(same_loop_alive, timeout=float(grace))
        for task in pending:
            try:
                task.cancel()
            except RuntimeError:
                # Event loop may already be closing during test teardown.
                logger.debug("Task cancellation skipped due to closing event loop")
        if pending:
            # Drain canceled tasks to avoid unraisable coroutine warnings during loop teardown.
            await asyncio.gather(*pending, return_exceptions=True)
        _inflight_tasks.clear()
