"""Dead-man switch for cron/scheduler jobs.

Checks SchedulerJobRun table for jobs that should have run but haven't,
and jobs with consecutive failures exceeding the alert threshold.
Returns a health report with actionable alerts.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ceo_control import SchedulerJobRun

logger = logging.getLogger(__name__)

# Expected jobs and their max tolerable silence (minutes).
_EXPECTED_JOBS: dict[str, int] = {
    "clickup_sync": 120,
    "github_sync": 120,
    "slack_sync": 120,
    "google_calendar_sync": 120,
    "digitalocean_sync": 240,
    "notion_sync": 240,
    "calendly_sync": 240,
    "google_analytics_sync": 480,
    "stripe_sync": 480,
    "hubspot_sync": 480,
}


async def get_cron_health(db: AsyncSession, org_id: int) -> dict:
    """Return dead-man switch health report for all expected cron jobs."""
    now = datetime.now(UTC)
    threshold = settings.SYNC_FAILURE_ALERT_THRESHOLD

    # Get latest run per job
    subq = (
        select(
            SchedulerJobRun.job_name,
            func.max(SchedulerJobRun.started_at).label("last_run"),
        )
        .where(SchedulerJobRun.organization_id == org_id)
        .group_by(SchedulerJobRun.job_name)
        .subquery()
    )
    rows = (await db.execute(select(subq))).all()
    latest_by_job: dict[str, datetime] = {r.job_name: r.last_run for r in rows}

    # Get recent failure streaks
    recent_runs = (
        await db.execute(
            select(SchedulerJobRun)
            .where(
                SchedulerJobRun.organization_id == org_id,
                SchedulerJobRun.started_at >= now - timedelta(hours=48),
            )
            .order_by(SchedulerJobRun.started_at.desc())
        )
    ).scalars().all()

    runs_by_job: dict[str, list[SchedulerJobRun]] = {}
    for run in recent_runs:
        runs_by_job.setdefault(run.job_name, []).append(run)

    alerts: list[dict] = []
    jobs: list[dict] = []

    for job_name, max_silence_min in _EXPECTED_JOBS.items():
        last_run = latest_by_job.get(job_name)
        silent_minutes = int((now - last_run).total_seconds() / 60) if last_run else None

        # Failure streak
        job_runs = runs_by_job.get(job_name, [])
        streak = 0
        for run in job_runs:
            if run.status == "error":
                streak += 1
            else:
                break

        status = "healthy"
        if last_run is None:
            status = "never_run"
        elif silent_minutes and silent_minutes > max_silence_min:
            status = "silent"
            alerts.append({
                "job": job_name,
                "type": "silent",
                "message": f"{job_name} has not run in {silent_minutes} min (threshold: {max_silence_min})",
                "last_run": last_run.isoformat(),
            })
        if streak >= threshold:
            status = "failing"
            alerts.append({
                "job": job_name,
                "type": "streak",
                "message": f"{job_name} has {streak} consecutive failures",
                "last_run": last_run.isoformat() if last_run else None,
            })

        jobs.append({
            "job_name": job_name,
            "status": status,
            "last_run": last_run.isoformat() if last_run else None,
            "silent_minutes": silent_minutes,
            "max_silence_minutes": max_silence_min,
            "failure_streak": streak,
        })

    overall = "healthy"
    if any(a["type"] == "streak" for a in alerts):
        overall = "degraded"
    if any(a["type"] == "silent" for a in alerts):
        overall = "unhealthy"

    report = {
        "status": overall,
        "checked_at": now.isoformat(),
        "alert_count": len(alerts),
        "alerts": alerts,
        "jobs": jobs,
    }

    if alerts:
        logger.warning("Cron dead-man switch: %d alerts — %s", len(alerts), overall)
    return report
