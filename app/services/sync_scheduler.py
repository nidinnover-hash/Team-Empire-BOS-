"""
Background sync scheduler — periodically syncs all connected integrations
(ClickUp, GitHub, Slack) so the AI always has fresh context.

Two modes:
  1. Scheduled: runs every SYNC_INTERVAL_MINUTES (default 30) in the background.
  2. On-demand: call trigger_sync_for_org(org_id) from login / dashboard load;
     a per-org throttle prevents redundant syncs within THROTTLE_MINUTES.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from contextlib import asynccontextmanager

from app.db.session import AsyncSessionLocal  # noqa: E402 - imported here so tests can patch it
from app.models.ceo_control import SchedulerJobRun

logger = logging.getLogger(__name__)

@asynccontextmanager
async def _db_session_with_retry(max_retries: int = 3, base_delay: float = 2.0):
    """Acquire an AsyncSession with exponential backoff on connection failure."""
    for attempt in range(max_retries):
        try:
            async with AsyncSessionLocal() as db:
                yield db
                return
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning("DB connection attempt %d/%d failed, retrying in %.1fs: %s", attempt + 1, max_retries, delay, exc)
            await asyncio.sleep(delay)

# Per-org throttle: don't fire on-demand sync more than once per N minutes.
# Default 15 — overridden by settings.SYNC_THROTTLE_MINUTES at runtime.
_last_synced: dict[int, datetime] = {}
_last_ceo_summary_date_by_org: dict[int, str] = {}
_last_pending_digest_date_by_org: dict[int, str] = {}


def get_last_synced_for_org(org_id: int) -> datetime | None:
    """Return the last sync timestamp for an org, or None if never synced."""
    return _last_synced.get(org_id)


def _throttle_minutes() -> int:
    try:
        from app.core.config import settings
        value = int(settings.SYNC_THROTTLE_MINUTES)
        return max(value, 0)
    except (ImportError, AttributeError, TypeError, ValueError):
        return 15


def _format_briefing_summary(summary: object) -> str:
    """Render executive summary payload to readable text for daily context."""
    if isinstance(summary, str):
        return summary
    if isinstance(summary, dict):
        lines = [
            f"Total members: {summary.get('total_members', 0)}",
            f"With plans: {summary.get('members_with_plan', 0)}",
            f"Tasks today: {summary.get('total_tasks_today', 0)}",
            f"Tasks done: {summary.get('tasks_done', 0)}",
            f"Pending approvals: {summary.get('pending_approvals', 0)}",
            f"Unread emails: {summary.get('unread_emails', 0)}",
        ]
        members_without_plan = summary.get("members_without_plan", [])
        if members_without_plan:
            lines.append("Missing plan: " + ", ".join(str(n) for n in members_without_plan))
        return "\n".join(lines)
    return "No briefing data."

# Background task handle (stored so we can cancel on shutdown)
_scheduler_task: asyncio.Task | None = None
_inflight_tasks: set[asyncio.Task] = set()


def _task_error_handler(task: asyncio.Task) -> None:
    """Log unhandled exceptions from fire-and-forget tasks."""
    _inflight_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Background task failed: %s: %s", type(exc).__name__, exc)


def _severity_rank(value: object) -> int:
    text = str(value or "").strip().upper()
    return {"CRITICAL": 0, "HIGH": 1, "MED": 2, "LOW": 3}.get(text, 4)


def _extract_top_risks(report: dict[str, object], limit: int = 5) -> list[dict[str, object]]:
    rows = report.get("violations")
    if not isinstance(rows, list):
        return []

    parsed: list[dict[str, object]] = [item for item in rows if isinstance(item, dict)]
    parsed.sort(
        key=lambda row: (
            _severity_rank(row.get("severity")),
            str(row.get("created_at") or ""),
        ),
        reverse=False,
    )
    return parsed[: max(limit, 0)]


def _format_ceo_risk_digest(
    org_id: int,
    top_risks: list[dict[str, object]],
    stale_integrations: list[dict[str, object]],
    generated_at: str,
) -> str:
    lines = [
        f"CEO Daily Risk Digest (org {org_id})",
        f"Generated: {generated_at}",
        "",
        "Top Risks:",
    ]
    if not top_risks:
        lines.append("- No open high-priority violations.")
    else:
        for item in top_risks:
            lines.append(
                f"- [{item.get('severity', 'MED')}] {item.get('title', 'Policy issue')} ({item.get('platform', 'unknown')})"
            )
    lines.append("")
    lines.append("Integration SLA Alerts:")
    if not stale_integrations:
        lines.append("- All connected integrations are within SLA.")
    else:
        for row in stale_integrations:
            age_hours = row.get("age_hours")
            suffix = f"{age_hours}h stale" if age_hours is not None else "never synced"
            status = row.get("last_sync_status") or "unknown"
            lines.append(f"- {row.get('type', 'integration')}: {suffix} (status={status})")
    lines.append("")
    lines.append("Mode: suggest_only (no auto-blocking actions)")
    return "\n".join(lines)


async def _collect_stale_integrations(
    db: AsyncSession,
    org_id: int,
) -> list[dict[str, object]]:
    from sqlalchemy import select
    from app.core.config import settings
    from app.models.integration import Integration

    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(settings.SYNC_STALE_HOURS))
    rows = (
        await db.execute(
            select(Integration).where(
                Integration.organization_id == org_id,
                Integration.status == "connected",
            )
        )
    ).scalars().all()

    alerts: list[dict[str, object]] = []
    now = datetime.now(timezone.utc)
    for item in rows:
        if item.last_sync_status == "error":
            alerts.append(
                {
                    "type": item.type,
                    "age_hours": (
                        round((now - item.last_sync_at).total_seconds() / 3600, 1)
                        if item.last_sync_at else None
                    ),
                    "last_sync_status": item.last_sync_status,
                }
            )
            continue
        if item.last_sync_at is None or item.last_sync_at < cutoff:
            alerts.append(
                {
                    "type": item.type,
                    "age_hours": (
                        round((now - item.last_sync_at).total_seconds() / 3600, 1)
                        if item.last_sync_at else None
                    ),
                    "last_sync_status": item.last_sync_status,
                }
            )
    return alerts


async def _record_job_run(
    db: AsyncSession,
    *,
    org_id: int,
    job_name: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    details: dict[str, object] | None = None,
    error: str | None = None,
) -> None:
    if not hasattr(db, "add"):
        return
    details_json = "{}"
    if details:
        try:
            details_json = json.dumps(details)
        except Exception:
            details_json = "{}"
    duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    db.add(
        SchedulerJobRun(
            organization_id=org_id,
            job_name=job_name,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            details_json=details_json,
            error=(error or None),
        )
    )


async def _maybe_send_daily_ceo_slack_summary(
    db: AsyncSession,
    org_id: int,
    top_risks: list[dict[str, object]],
    stale_integrations: list[dict[str, object]],
    generated_at: str,
) -> None:
    from app.core.config import settings
    from app.services import slack_service

    channel_id = (settings.CEO_ALERTS_SLACK_CHANNEL_ID or "").strip()
    if not channel_id:
        return
    message = _format_ceo_risk_digest(
        org_id=org_id,
        top_risks=top_risks,
        stale_integrations=stale_integrations,
        generated_at=generated_at,
    )
    try:
        await slack_service.send_to_slack(db, org_id=org_id, channel_id=channel_id, text=message)
    except Exception as exc:
        logger.warning("Daily CEO Slack digest failed for org=%d: %s", org_id, type(exc).__name__)


# ── Core sync runner ──────────────────────────────────────────────────────────

async def _run_integrations(db: AsyncSession, org_id: int) -> None:
    """Sync all connected integrations for org_id. Logs but never raises."""
    from sqlalchemy import update
    from app.core.config import settings
    from app.models.integration import Integration
    from app.services import clickup_service, do_service, email_control, email_service, github_service, slack_service
    from app.services import compliance_engine
    from app.services.calendar_service import sync_calendar_events
    from app.core.resilience import run_with_retry

    async def _mark_status(int_type: str, status: str) -> None:
        try:
            await db.execute(
                update(Integration)
                .where(Integration.organization_id == org_id, Integration.type == int_type)
                .values(last_sync_status=status)
            )
        except Exception:
            pass  # best-effort status tracking

    for name, fn in [
        ("clickup", clickup_service.sync_clickup_tasks),
        ("github", github_service.sync_github),
        ("digitalocean", do_service.sync_digitalocean),
        ("slack", slack_service.sync_slack_messages),
    ]:
        started = datetime.now(timezone.utc)
        try:
            result = await run_with_retry(
                lambda _fn=fn: _fn(db, org_id),  # type: ignore[misc]
                attempts=2,
                timeout_seconds=30.0,
                backoff_seconds=1.0,
            )
            logger.debug("Sync %s org=%d -> %s", name, org_id, result)
            await _mark_status(name, "ok")
            await _record_job_run(
                db,
                org_id=org_id,
                job_name=f"{name}_sync",
                status="ok",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                details={"result": result if isinstance(result, dict) else {"ok": True}},
            )
        except Exception as exc:
            logger.warning("Background %s sync failed org=%d: %s: %s", name, org_id, type(exc).__name__, str(exc)[:500])
            await _mark_status(name, "error")
            await _record_job_run(
                db,
                org_id=org_id,
                job_name=f"{name}_sync",
                status="error",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                error=f"{type(exc).__name__}: {str(exc)[:500]}",
            )

    # Email sync + control classification loop (best effort)
    started = datetime.now(timezone.utc)
    try:
        if getattr(settings, "FEATURE_EMAIL_SYNC", True):
            try:
                await email_service.sync_emails(db, org_id=org_id, actor_user_id=1)
            except Exception:
                pass
            control_result = await email_control.process_inbox_controls(
                db,
                org_id=org_id,
                actor_user_id=1,
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
                finished_at=datetime.now(timezone.utc),
                details={
                    "processed": processed if isinstance(processed, int) else 0,
                    "tasks_created": tasks_created if isinstance(tasks_created, int) else 0,
                    "approvals_created": approvals_created if isinstance(approvals_created, int) else 0,
                },
            )
    except Exception as exc:
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="email_control_loop",
            status="error",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
        )

    # Google Calendar sync - stored as DailyContext, auto-included in memory
    started = datetime.now(timezone.utc)
    try:
        result = await run_with_retry(
            lambda: sync_calendar_events(db, organization_id=org_id),
            attempts=2,
            timeout_seconds=30.0,
            backoff_seconds=1.0,
        )
        logger.debug("Sync calendar org=%d -> %s", org_id, result)
        await _mark_status("google_calendar", "ok")
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="google_calendar_sync",
            status="ok",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            details={"result": result if isinstance(result, dict) else {"ok": True}},
        )
    except Exception as exc:
        logger.warning("Background calendar sync failed org=%d: %s: %s", org_id, type(exc).__name__, str(exc)[:500])
        await _mark_status("google_calendar", "error")
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="google_calendar_sync",
            status="error",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
        )

    started = datetime.now(timezone.utc)
    try:
        # Suggest-only compliance scan: records violations, blocks nothing.
        report = await compliance_engine.run_compliance(db, org_id)
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="compliance_run",
            status="ok",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            details={"compliance_score": report.get("compliance_score")},
        )
        if hasattr(db, "commit"):
            await db.commit()
    except Exception as exc:
        await _record_job_run(
            db,
            org_id=org_id,
            job_name="compliance_run",
            status="error",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
        )
        if hasattr(db, "commit"):
            await db.commit()


async def replay_job_for_org(db: AsyncSession, org_id: int, job_name: str) -> dict[str, object]:
    """Manually replay a scheduler job for one organization."""
    from app.services import clickup_service, do_service, github_service, slack_service
    from app.services import compliance_engine
    from app.services.calendar_service import sync_calendar_events

    started = datetime.now(timezone.utc)
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
        elif job_name == "full_sync":
            await _run_integrations(db, org_id)
            result = {"ok": True}
        else:
            raise ValueError(f"Unsupported job_name: {job_name}")

        await _record_job_run(
            db,
            org_id=org_id,
            job_name=f"manual_{job_name}",
            status="ok",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            details={"result": result if isinstance(result, dict) else {"ok": True}},
        )
        await db.commit()
        return {"ok": True, "job_name": job_name, "result": result}
    except Exception as exc:
        await _record_job_run(
            db,
            org_id=org_id,
            job_name=f"manual_{job_name}",
            status="error",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
        )
        await db.commit()
        return {"ok": False, "job_name": job_name, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}

async def trigger_sync_for_org(org_id: int) -> None:
    """
    Fire-and-forget sync for a single org.
    Skips silently if the same org was synced within THROTTLE_MINUTES.
    Safe to call from login/dashboard without awaiting.
    """
    now = datetime.now(timezone.utc)
    last = _last_synced.get(org_id)
    if last and (now - last).total_seconds() < _throttle_minutes() * 60:
        logger.debug("Sync throttled for org=%d (last=%s)", org_id, last.isoformat())
        return

    _MAX_INFLIGHT = 50
    if len(_inflight_tasks) >= _MAX_INFLIGHT:
        logger.warning("Inflight task cap reached (%d), skipping sync for org=%d", _MAX_INFLIGHT, org_id)
        return

    _last_synced[org_id] = now

    async def _do():
        try:
            async with AsyncSessionLocal() as db:
                await _run_integrations(db, org_id)
        except Exception as exc:
            logger.error("On-demand sync error org=%d: %s", org_id, exc)

    task = asyncio.create_task(_do())
    _inflight_tasks.add(task)
    task.add_done_callback(_task_error_handler)


# ── Periodic scheduler loop ───────────────────────────────────────────────────

async def _check_morning_briefing(db: AsyncSession, org_id: int) -> None:
    """Generate daily briefing at 8-9am IST if not already created today."""
    from sqlalchemy import select
    from app.models.memory import DailyContext

    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(timezone.utc).astimezone(tz)
    if local_now.hour < 8 or local_now.hour >= 9:
        return

    today_ist = local_now.date()

    # Check if auto briefing already exists for today (IST date, not server-local)
    result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == org_id,
            DailyContext.date == today_ist,
            DailyContext.context_type == "auto_briefing",
        ).limit(1)
    )
    if result.scalar_one_or_none():
        return

    try:
        from app.services import briefing as briefing_service
        from app.services import memory as memory_service
        from app.schemas.memory import DailyContextCreate

        executive = await briefing_service.get_executive_briefing(db, org_id=org_id)
        summary = executive.get("summary") or executive.get("team_summary") or "No briefing data."
        summary_text = _format_briefing_summary(summary)

        await memory_service.add_daily_context(
            db=db,
            organization_id=org_id,
            data=DailyContextCreate(
                date=today_ist,
                context_type="auto_briefing",
                content=f"Morning auto-briefing:\n{summary_text}",
                related_to="scheduler",
            ),
        )
        logger.info("Morning briefing generated for org=%d", org_id)
    except Exception as exc:
        logger.warning("Morning briefing failed for org=%d: %s", org_id, type(exc).__name__)


async def _maybe_generate_daily_ceo_summary(db: AsyncSession, org_id: int) -> None:
    from app.models.ceo_control import CEOSummary
    from app.services import compliance_engine
    from app.core.config import settings

    tz = ZoneInfo(settings.CEO_SUMMARY_TIMEZONE)
    local_now = datetime.now(timezone.utc).astimezone(tz)
    # Run once per local day after 09:00 in the configured timezone.
    if local_now.hour < 9:
        return
    day_key = local_now.strftime("%Y-%m-%d")
    if _last_ceo_summary_date_by_org.get(org_id) == day_key:
        return
    started = datetime.now(timezone.utc)
    report = await compliance_engine.latest_report(db, org_id)
    top_risks = _extract_top_risks(report, limit=5)
    stale_integrations = await _collect_stale_integrations(db, org_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    db.add(
        CEOSummary(
            organization_id=org_id,
            summary_json=json.dumps(
                {
                    "generated_at": generated_at,
                    "report_count": report.get("count", 0),
                    "top_violations": top_risks,
                    "stale_integrations": stale_integrations,
                }
            ),
            created_at=datetime.now(timezone.utc),
        )
    )
    _last_ceo_summary_date_by_org[org_id] = day_key
    await _record_job_run(
        db,
        org_id=org_id,
        job_name="daily_ceo_summary",
        status="ok",
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        details={"top_risks_count": len(top_risks), "stale_integrations_count": len(stale_integrations)},
    )
    await db.commit()
    await _maybe_send_daily_ceo_slack_summary(
        db=db,
        org_id=org_id,
        top_risks=top_risks,
        stale_integrations=stale_integrations,
        generated_at=generated_at,
    )


async def _maybe_generate_daily_pending_digest(db: AsyncSession, org_id: int) -> None:
    from app.core.config import settings
    from app.services import email_control

    if not settings.EMAIL_CONTROL_DIGEST_ENABLED:
        return
    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(timezone.utc).astimezone(tz)
    if local_now.hour < settings.EMAIL_CONTROL_DIGEST_HOUR_IST:
        return
    if (
        local_now.hour == settings.EMAIL_CONTROL_DIGEST_HOUR_IST
        and local_now.minute < settings.EMAIL_CONTROL_DIGEST_MINUTE_IST
    ):
        return
    day_key = local_now.strftime("%Y-%m-%d")
    if _last_pending_digest_date_by_org.get(org_id) == day_key:
        return
    await email_control.draft_pending_actions_digest_email(
        db=db,
        org_id=org_id,
        actor_user_id=1,
    )
    _last_pending_digest_date_by_org[org_id] = day_key


async def _cleanup_old_chat_messages(db: AsyncSession, org_id: int) -> None:
    """Delete chat messages older than CHAT_HISTORY_RETENTION_DAYS."""
    from datetime import timedelta
    from sqlalchemy import delete
    from app.core.config import settings
    from app.models.chat_message import ChatMessage

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.CHAT_HISTORY_RETENTION_DAYS)
    try:
        result = await db.execute(
            delete(ChatMessage).where(
                ChatMessage.organization_id == org_id,
                ChatMessage.created_at < cutoff,
            )
        )
        if result.rowcount:
            logger.info("Cleaned up %d old chat messages for org=%d", result.rowcount, org_id)
            await db.commit()
    except Exception as exc:
        logger.debug("Chat cleanup failed for org=%d: %s", org_id, exc)


async def _scheduler_loop(interval_minutes: int) -> None:
    """Runs forever; wakes up every interval_minutes and syncs all orgs."""
    from app.services.organization import list_organizations

    logger.info("Sync scheduler started (interval=%d min)", interval_minutes)
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            async with AsyncSessionLocal() as db:
                orgs = await list_organizations(db)
            for org in orgs:
                try:
                    async with AsyncSessionLocal() as db:
                        await _run_integrations(db, org.id)
                        await _check_morning_briefing(db, org.id)
                        await _maybe_generate_daily_ceo_summary(db, org.id)
                        await _maybe_generate_daily_pending_digest(db, org.id)
                        await _cleanup_old_chat_messages(db, org.id)
                        _last_synced[org.id] = datetime.now(timezone.utc)
                except Exception as exc:
                    logger.warning("Sync failed for org=%d: %s", org.id, exc)
            logger.info("Scheduled sync complete (%d org(s))", len(orgs))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Scheduled sync loop error: %s", exc)


def start_scheduler(interval_minutes: int = 30) -> asyncio.Task:
    """
    Create and return the background asyncio task.
    Call once from the FastAPI lifespan context manager.
    """
    global _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop(interval_minutes))
    return _scheduler_task


async def stop_scheduler() -> None:
    """Cancel the scheduler and await in-flight sync tasks on shutdown."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None

    # Wait for any in-flight on-demand syncs to finish
    if _inflight_tasks:
        from app.core.config import settings

        grace = settings.SHUTDOWN_GRACE_SECONDS
        alive = {t for t in _inflight_tasks if not t.done()}
        if not alive:
            _inflight_tasks.clear()
            return

        logger.info("Awaiting %d in-flight sync tasks (grace=%ds)...", len(alive), grace)
        _done, pending = await asyncio.wait(alive, timeout=float(grace))
        for task in pending:
            try:
                task.cancel()
            except RuntimeError:
                # Event loop may already be closing during test teardown.
                pass
        _inflight_tasks.clear()
