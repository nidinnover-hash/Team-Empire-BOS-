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
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal  # noqa: E402 - imported here so tests can patch it

logger = logging.getLogger(__name__)

# Per-org throttle: don't fire on-demand sync more than once per N minutes.
# Default 15 — overridden by settings.SYNC_THROTTLE_MINUTES at runtime.
_last_synced: dict[int, datetime] = {}


def _throttle_minutes() -> int:
    try:
        from app.core.config import settings
        return settings.SYNC_THROTTLE_MINUTES
    except Exception:
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


# ── Core sync runner ──────────────────────────────────────────────────────────

async def _run_integrations(db: AsyncSession, org_id: int) -> None:
    """Sync all connected integrations for org_id. Logs but never raises."""
    from app.services import clickup_service, github_service, slack_service
    from app.services.calendar_service import sync_calendar_events

    for name, fn in [
        ("clickup", clickup_service.sync_clickup_tasks),
        ("github", github_service.sync_github),
        ("slack", slack_service.sync_slack_messages),
    ]:
        try:
            result = await fn(db, org_id)
            logger.debug("Sync %s org=%d → %s", name, org_id, result)
        except Exception as exc:
            logger.warning("Background %s sync failed org=%d: %s", name, org_id, type(exc).__name__)

    # Google Calendar sync — stored as DailyContext, auto-included in memory
    try:
        result = await sync_calendar_events(db, organization_id=org_id)
        logger.debug("Sync calendar org=%d → %s", org_id, result)
    except Exception as exc:
        logger.warning("Background calendar sync failed org=%d: %s", org_id, type(exc).__name__)


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

    asyncio.create_task(_do())


# ── Periodic scheduler loop ───────────────────────────────────────────────────

async def _check_morning_briefing(db: AsyncSession, org_id: int) -> None:
    """Generate daily briefing at 8-9am if not already created today."""
    from datetime import date
    from sqlalchemy import select
    from app.models.memory import DailyContext

    now = datetime.now(timezone.utc)
    hour = now.hour
    if hour < 8 or hour >= 9:
        return

    # Check if auto briefing already exists for today
    result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == org_id,
            DailyContext.date == date.today(),
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
                date=date.today(),
                context_type="auto_briefing",
                content=f"Morning auto-briefing:\n{summary_text}",
                related_to="scheduler",
            ),
        )
        logger.info("Morning briefing generated for org=%d", org_id)
    except Exception as exc:
        logger.warning("Morning briefing failed for org=%d: %s", org_id, type(exc).__name__)


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
                    await _run_integrations(db, org.id)
                    await _check_morning_briefing(db, org.id)
                    _last_synced[org.id] = datetime.now(timezone.utc)
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


def stop_scheduler() -> None:
    """Cancel the background task on shutdown."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
