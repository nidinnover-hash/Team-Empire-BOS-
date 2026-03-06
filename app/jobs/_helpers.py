"""Shared helpers for scheduler jobs."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import IntegrationSyncError
from app.models.ceo_control import SchedulerJobRun
from app.platform.signals import (
    SCHEDULER_JOB_COMPLETED,
    SCHEDULER_JOB_FAILED,
    SignalCategory,
    SignalEnvelope,
    publish_signal,
)

logger = logging.getLogger(__name__)


def scheduler_error_category(exc: Exception) -> str:
    if isinstance(exc, SQLAlchemyError):
        return "database_error"
    if isinstance(exc, IntegrationSyncError):
        return "integration_sync_error"
    if isinstance(exc, TimeoutError | ConnectionError):
        return "network_error"
    if isinstance(exc, ImportError | AttributeError):
        return "dependency_error"
    if isinstance(exc, ValueError | TypeError):
        return "validation_error"
    if isinstance(exc, OSError):
        return "os_error"
    return "runtime_error"


async def record_job_run(
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
        except (TypeError, ValueError):
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
    await publish_signal(
        SignalEnvelope(
            topic=SCHEDULER_JOB_FAILED if status == "error" else SCHEDULER_JOB_COMPLETED,
            category=SignalCategory.SYSTEM,
            organization_id=org_id,
            source="sync_scheduler",
            entity_type="scheduler_job",
            entity_id=job_name,
            summary_text=f"{job_name}:{status}",
            payload={
                "job_name": job_name,
                "status": status,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_ms": duration_ms,
                "details": details or {},
                "error": error,
            },
        ),
        db=db,
    )
