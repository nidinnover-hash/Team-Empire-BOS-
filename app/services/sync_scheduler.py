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

from app.db.session import AsyncSessionLocal  # noqa: E402 - imported here so tests can patch it

logger = logging.getLogger(__name__)

# Per-org throttle: don't fire on-demand sync more than once per N minutes.
# Default 15 — overridden by settings.SYNC_THROTTLE_MINUTES at runtime.
_last_synced: dict[int, datetime] = {}
_last_ceo_summary_date_by_org: dict[int, str] = {}


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
    from app.models.integration import Integration
    from app.services import clickup_service, do_service, github_service, slack_service
    from app.services import compliance_engine
    from app.services.calendar_service import sync_calendar_events

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
        try:
            result = await fn(db, org_id)
            logger.debug("Sync %s org=%d → %s", name, org_id, result)
            await _mark_status(name, "ok")
        except Exception as exc:
            logger.warning("Background %s sync failed org=%d: %s", name, org_id, type(exc).__name__)
            await _mark_status(name, "error")

    # Google Calendar sync — stored as DailyContext, auto-included in memory
    try:
        result = await sync_calendar_events(db, organization_id=org_id)
        logger.debug("Sync calendar org=%d → %s", org_id, result)
        await _mark_status("google_calendar", "ok")
    except Exception as exc:
        logger.warning("Background calendar sync failed org=%d: %s", org_id, type(exc).__name__)
        await _mark_status("google_calendar", "error")

    try:
        # Suggest-only compliance scan: records violations, blocks nothing.
        await compliance_engine.run_compliance(db, org_id)
        await db.commit()
    except Exception:
        pass


# ── On-demand (throttled) trigger ────────────────────────────────────────────

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
    await db.commit()
    await _maybe_send_daily_ceo_slack_summary(
        db=db,
        org_id=org_id,
        top_risks=top_risks,
        stale_integrations=stale_integrations,
        generated_at=generated_at,
    )


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
        logger.info("Awaiting %d in-flight sync tasks (grace=%ds)…", len(_inflight_tasks), grace)
        done, pending = await asyncio.wait(_inflight_tasks, timeout=float(grace))
        for t in pending:
            t.cancel()
        _inflight_tasks.clear()
