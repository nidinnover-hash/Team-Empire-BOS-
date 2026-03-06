"""Monitoring jobs — health checks, goal deadlines, stale tasks, SLO evaluation."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs._helpers import record_job_run, scheduler_error_category
from app.models.ceo_control import SchedulerJobRun

logger = logging.getLogger(__name__)

_last_scheduler_slo_alert_key_by_org: dict[int, str] = {}


async def check_token_health_job(db: AsyncSession, org_id: int) -> None:
    """Check integration token health and emit notifications for unhealthy tokens."""
    from app.services.notification import create_notification
    from app.services.token_health import check_token_health

    started = datetime.now(UTC)
    try:
        results = await check_token_health(db, org_id)
        unhealthy = [r for r in results if r.get("status") != "healthy"]
        for item in unhealthy:
            await create_notification(
                db, organization_id=org_id,
                type="token_health_warning",
                severity="warning" if item.get("status") != "expired" else "high",
                title=f"Token {item.get('status', 'issue')}: {item.get('type', 'unknown')}",
                message=str(item.get("recommendation", "Check integration token.")),
                source="token_health",
            )
        if unhealthy:
            await db.commit()
        await record_job_run(
            db, org_id=org_id, job_name="token_health_check", status="ok",
            started_at=started, finished_at=datetime.now(UTC),
            details={"checked": len(results), "unhealthy": len(unhealthy)},
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Token health check failed org=%d category=%s error_type=%s",
            org_id, scheduler_error_category(exc), type(exc).__name__, exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="token_health_check", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        await db.commit()


async def check_goal_deadlines(db: AsyncSession, org_id: int) -> None:
    """Emit warnings for active goals whose target_date is within 3 days or overdue."""
    from app.models.goal import Goal
    from app.services.notification import create_notification

    started = datetime.now(UTC)
    try:
        today = datetime.now(UTC).date()
        warn_horizon = today + timedelta(days=3)
        result = await db.execute(
            select(Goal).where(
                Goal.organization_id == org_id,
                Goal.status == "active",
                Goal.target_date.isnot(None),
                Goal.target_date <= warn_horizon,
            )
        )
        goals = list(result.scalars().all())
        for goal in goals:
            if goal.target_date is None:
                continue
            overdue = goal.target_date < today
            sev = "error" if overdue else "warning"
            label = "OVERDUE" if overdue else "Due Soon"
            await create_notification(
                db, organization_id=org_id, type="goal_deadline", severity=sev,
                title=f"Goal {label}: {goal.title}",
                message=f"Target date {goal.target_date.isoformat()} — progress {goal.progress}%.",
                source="scheduler", entity_type="goal", entity_id=goal.id,
            )
        if goals:
            await db.commit()
        await record_job_run(
            db, org_id=org_id, job_name="goal_deadline_check", status="ok",
            started_at=started, finished_at=datetime.now(UTC),
            details={"checked": len(goals), "overdue": sum(1 for g in goals if g.target_date and g.target_date < today)},
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Goal deadline check failed org=%d category=%s error_type=%s",
            org_id, scheduler_error_category(exc), type(exc).__name__, exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="goal_deadline_check", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        await db.commit()


async def check_stale_tasks(db: AsyncSession, org_id: int) -> None:
    """Emit notifications for tasks that are overdue or stale (no update in 7+ days)."""
    from app.models.task import Task
    from app.services.notification import create_notification

    started = datetime.now(UTC)
    try:
        today = datetime.now(UTC)
        stale_cutoff = today - timedelta(days=7)

        overdue_result = await db.execute(
            select(Task).where(
                Task.organization_id == org_id,
                Task.is_done.is_(False),
                Task.due_date.isnot(None),
                Task.due_date < today,
            ).limit(50)
        )
        overdue_tasks = list(overdue_result.scalars().all())

        for task in overdue_tasks:
            await create_notification(
                db, organization_id=org_id, type="stale_task", severity="warning",
                title=f"Overdue task: {task.title}",
                message=f"Due date was {task.due_date.isoformat() if task.due_date else 'unknown'}.",
                source="scheduler", entity_type="task", entity_id=task.id,
            )

        stale_result = await db.execute(
            select(Task).where(
                Task.organization_id == org_id,
                Task.is_done.is_(False),
                Task.updated_at < stale_cutoff,
            ).limit(50)
        )
        stale_tasks = list(stale_result.scalars().all())

        for task in stale_tasks:
            if task.due_date and task.due_date < today:
                continue
            await create_notification(
                db, organization_id=org_id, type="stale_task", severity="info",
                title=f"Stale task: {task.title}",
                message="No updates in 7+ days. Consider closing or updating.",
                source="scheduler", entity_type="task", entity_id=task.id,
            )

        total = len(overdue_tasks) + len(stale_tasks)
        if total:
            await db.commit()
        await record_job_run(
            db, org_id=org_id, job_name="stale_task_check", status="ok",
            started_at=started, finished_at=datetime.now(UTC),
            details={"overdue": len(overdue_tasks), "stale": len(stale_tasks)},
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Stale task check failed org=%d category=%s",
            org_id, scheduler_error_category(exc), exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="stale_task_check", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        await db.commit()


async def check_follow_up_contacts(db: AsyncSession, org_id: int) -> None:
    """Emit notifications for contacts whose follow-up date is due."""
    from app.services.contact import get_follow_up_due
    from app.services.notification import create_notification

    started = datetime.now(UTC)
    try:
        due_contacts = await get_follow_up_due(db, org_id, limit=20)
        for contact in due_contacts:
            await create_notification(
                db, organization_id=org_id, type="contact_follow_up", severity="info",
                title=f"Follow-up due: {contact.name}",
                message=f"Pipeline: {contact.pipeline_stage}. Score: {contact.lead_score}.",
                source="scheduler", entity_type="contact", entity_id=contact.id,
            )
        if due_contacts:
            await db.commit()
        await record_job_run(
            db, org_id=org_id, job_name="contact_follow_up_check", status="ok",
            started_at=started, finished_at=datetime.now(UTC),
            details={"due": len(due_contacts)},
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Contact follow-up check failed org=%d category=%s",
            org_id, scheduler_error_category(exc), exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="contact_follow_up_check", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        await db.commit()


async def monitor_scheduler_slos(db: AsyncSession, org_id: int) -> None:
    """Evaluate lightweight scheduler SLOs and emit at most one alert per org/day."""
    from app.services.notification import create_notification

    now = datetime.now(UTC)
    day_key = now.strftime("%Y-%m-%d")
    if _last_scheduler_slo_alert_key_by_org.get(org_id) == day_key:
        return
    window_start = now - timedelta(hours=24)
    rows = (
        (
            await db.execute(
                select(SchedulerJobRun).where(
                    SchedulerJobRun.organization_id == org_id,
                    SchedulerJobRun.started_at >= window_start,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return
    total = len(rows)
    success = sum(1 for row in rows if str(row.status) == "ok")
    success_rate = float(success / total) if total > 0 else 1.0
    durations = sorted(int(row.duration_ms or 0) for row in rows if row.duration_ms is not None)
    p95_ms = durations[min(len(durations) - 1, int(0.95 * (len(durations) - 1)))] if durations else 0
    stale_runs = sum(1 for row in rows if row.finished_at is None and (now - row.started_at).total_seconds() > 1800)
    breaches: list[str] = []
    if success_rate < 0.97:
        breaches.append(f"success_rate={success_rate:.3f}<0.97")
    if p95_ms > 30_000:
        breaches.append(f"p95_duration_ms={p95_ms}>30000")
    if stale_runs > 0:
        breaches.append(f"stale_runs={stale_runs}>0")
    if not breaches:
        return
    await create_notification(
        db, organization_id=org_id, type="scheduler_slo_breach",
        severity="warning", title="Scheduler SLO breach detected",
        message="; ".join(breaches), source="sync_scheduler", entity_type="scheduler",
    )
    _last_scheduler_slo_alert_key_by_org[org_id] = day_key
    await db.commit()
