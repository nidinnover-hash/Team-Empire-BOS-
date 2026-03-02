"""
Maintenance jobs — housekeeping tasks that run on every scheduler cycle.

Each function is a self-contained async job that:
  - accepts (db: AsyncSession, org_id: int)
  - logs but never raises
  - commits its own changes
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def cleanup_old_chat_messages(db: AsyncSession, org_id: int) -> None:
    """Delete chat messages older than CHAT_HISTORY_RETENTION_DAYS."""
    from sqlalchemy import delete

    from app.core.config import settings
    from app.models.chat_message import ChatMessage

    cutoff = datetime.now(UTC) - timedelta(days=settings.CHAT_HISTORY_RETENTION_DAYS)
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
    except SQLAlchemyError as exc:
        logger.debug("Chat cleanup failed for org=%d: %s", org_id, exc)


async def cleanup_old_logs(db: AsyncSession, org_id: int) -> None:
    """Delete AI call logs and decision traces older than 90 days."""
    from sqlalchemy import delete

    from app.models.ai_call_log import AiCallLog
    from app.models.decision_trace import DecisionTrace

    cutoff = datetime.now(UTC) - timedelta(days=90)
    try:
        for model, name in [(AiCallLog, "ai_call_logs"), (DecisionTrace, "decision_traces")]:
            result = await db.execute(
                delete(model).where(
                    model.organization_id == org_id,  # type: ignore[attr-defined]
                    model.created_at < cutoff,  # type: ignore[attr-defined]
                )
            )
            if result.rowcount:
                logger.info("Cleaned up %d old %s for org=%d", result.rowcount, name, org_id)
        await db.commit()
    except SQLAlchemyError as exc:
        logger.debug("Log cleanup failed for org=%d: %s", org_id, exc)


async def cleanup_old_job_runs_and_snapshots(db: AsyncSession, org_id: int) -> None:
    """Delete scheduler_job_runs and integration snapshots older than 90 days."""
    from sqlalchemy import delete

    from app.models.ceo_control import (
        ClickUpTaskSnapshot,
        DigitalOceanCostSnapshot,
        DigitalOceanDropletSnapshot,
        DigitalOceanTeamSnapshot,
        GitHubPRSnapshot,
        GitHubRepoSnapshot,
        GitHubRoleSnapshot,
        SchedulerJobRun,
    )

    cutoff = datetime.now(UTC) - timedelta(days=90)
    tables: list[tuple[Any, str, str]] = [
        (SchedulerJobRun, "scheduler_job_runs", "started_at"),
        (GitHubRoleSnapshot, "github_role_snapshot", "synced_at"),
        (GitHubRepoSnapshot, "github_repo_snapshot", "synced_at"),
        (GitHubPRSnapshot, "github_pr_snapshot", "synced_at"),
        (ClickUpTaskSnapshot, "clickup_tasks_snapshot", "synced_at"),
        (DigitalOceanDropletSnapshot, "do_droplet_snapshot", "synced_at"),
        (DigitalOceanTeamSnapshot, "do_team_snapshot", "synced_at"),
        (DigitalOceanCostSnapshot, "do_cost_snapshot", "synced_at"),
    ]
    try:
        for model, name, ts_col in tables:
            model_cls = model
            result = await db.execute(
                delete(model_cls).where(
                    model_cls.organization_id == org_id,
                    getattr(model_cls, ts_col) < cutoff,
                )
            )
            if result.rowcount:
                logger.info("Cleaned up %d old %s for org=%d", result.rowcount, name, org_id)
        await db.commit()
    except SQLAlchemyError as exc:
        logger.debug("Job run / snapshot cleanup failed for org=%d: %s", org_id, exc)


async def cleanup_old_trend_events(db: AsyncSession, org_id: int) -> None:
    """Delete trend telemetry events older than TREND_RETENTION_DAYS."""
    from sqlalchemy import delete

    from app.core.config import settings
    from app.models.event import Event
    from app.services.trend_telemetry import GOVERNANCE_EVENT, INCIDENT_EVENT, SECURITY_EVENT

    cutoff = datetime.now(UTC) - timedelta(days=settings.TREND_RETENTION_DAYS)
    trend_types = (SECURITY_EVENT, GOVERNANCE_EVENT, INCIDENT_EVENT)
    try:
        result = await db.execute(
            delete(Event).where(
                Event.organization_id == org_id,
                Event.event_type.in_(trend_types),
                Event.created_at < cutoff,
            )
        )
        if result.rowcount:
            logger.info("Cleaned up %d old trend events for org=%d", result.rowcount, org_id)
            await db.commit()
    except SQLAlchemyError as exc:
        logger.debug("Trend event cleanup failed for org=%d: %s", org_id, exc)
