"""Scheduled workflow automation — checks for due workflows and enqueues them.

Supports cron-like scheduling via trigger_spec_json:
  {
    "cron": "0 8 * * 1-5",        # standard cron (min hour dom month dow)
    "timezone": "Asia/Kolkata",    # optional, default UTC
    "interval_minutes": 60,        # alternative: run every N minutes
  }

The scheduler runs periodically (via sync_scheduler or job queue) and checks
which published scheduled workflows are due based on their last run time.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_run import WorkflowRun

logger = logging.getLogger(__name__)


def _parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of matching values."""
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            start = min_val if base == "*" else int(base)
            values.update(range(start, max_val + 1, step))
        elif "-" in part:
            lo, hi = part.split("-", 1)
            values.update(range(int(lo), int(hi) + 1))
        else:
            values.add(int(part))
    return values


def is_cron_due(cron_expr: str, now: datetime) -> bool:
    """Check if a cron expression matches the given datetime (minute granularity)."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False
    try:
        minutes = _parse_cron_field(parts[0], 0, 59)
        hours = _parse_cron_field(parts[1], 0, 23)
        days = _parse_cron_field(parts[2], 1, 31)
        months = _parse_cron_field(parts[3], 1, 12)
        dows = _parse_cron_field(parts[4], 0, 6)
    except (ValueError, IndexError):
        return False

    return (
        now.minute in minutes
        and now.hour in hours
        and now.day in days
        and now.month in months
        and now.weekday() in dows  # Python weekday: 0=Mon, cron: 0=Sun — adjust below
    )


def _cron_matches_now(cron_expr: str, now: datetime) -> bool:
    """Cron match with proper day-of-week handling (cron: 0=Sun, Python: 0=Mon)."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False
    try:
        minutes = _parse_cron_field(parts[0], 0, 59)
        hours = _parse_cron_field(parts[1], 0, 23)
        days = _parse_cron_field(parts[2], 1, 31)
        months = _parse_cron_field(parts[3], 1, 12)
        dows = _parse_cron_field(parts[4], 0, 6)
    except (ValueError, IndexError):
        return False

    # Convert Python weekday (0=Mon) to cron weekday (0=Sun)
    cron_dow = (now.weekday() + 1) % 7

    return (
        now.minute in minutes
        and now.hour in hours
        and now.day in days
        and now.month in months
        and cron_dow in dows
    )


async def _get_last_run_time(
    db: AsyncSession,
    definition_id: int,
    organization_id: int,
) -> datetime | None:
    """Get the most recent run start time for a workflow definition."""
    result = await db.execute(
        select(func.max(WorkflowRun.created_at))
        .where(
            WorkflowRun.workflow_definition_id == definition_id,
            WorkflowRun.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_scheduled_definitions(
    db: AsyncSession,
    organization_id: int,
) -> list[WorkflowDefinition]:
    """Get all published scheduled workflow definitions for an org."""
    result = await db.execute(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.organization_id == organization_id,
            WorkflowDefinition.status == "published",
            WorkflowDefinition.trigger_mode == "scheduled",
        )
    )
    return list(result.scalars().all())


def _is_definition_due(
    defn: WorkflowDefinition,
    now: datetime,
    last_run: datetime | None,
) -> bool:
    """Check if a scheduled definition is due for execution."""
    spec = defn.trigger_spec_json or {}

    # Cron-based scheduling
    cron_expr = spec.get("cron")
    if cron_expr:
        if not _cron_matches_now(cron_expr, now):
            return False
        # Ensure we haven't already run this minute
        return not (last_run and last_run.replace(second=0, microsecond=0) >= now.replace(second=0, microsecond=0))

    # Interval-based scheduling
    interval = spec.get("interval_minutes")
    if interval and isinstance(interval, int | float) and interval > 0:
        if last_run is None:
            return True
        return (now - last_run) >= timedelta(minutes=interval)

    return False


async def run_due_scheduled_workflows(organization_id: int) -> int:
    """Check all scheduled workflows for an org and enqueue those that are due.

    Returns the number of workflows enqueued.
    """
    from app.services.job_queue import enqueue

    factory = get_session_factory()
    count = 0
    now = datetime.now(UTC)

    async with factory() as db:
        definitions = await _get_scheduled_definitions(db, organization_id)

        for defn in definitions:
            last_run = await _get_last_run_time(db, defn.id, organization_id)

            if _is_definition_due(defn, now, last_run):
                await enqueue(
                    "run_workflow",
                    {
                        "organization_id": organization_id,
                        "workflow_definition_id": defn.id,
                        "input_json": defn.defaults_json or {},
                        "trigger_source": "scheduled",
                    },
                    db=db,
                )
                count += 1
                logger.info(
                    "Enqueued scheduled workflow %r (id=%d) for org %d",
                    defn.name, defn.id, organization_id,
                )

        if count:
            await db.commit()

    return count
