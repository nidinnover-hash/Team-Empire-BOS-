"""Telemetry jobs — trend and layer score snapshots."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs._helpers import record_job_run, scheduler_error_category
from app.services import trend_telemetry

logger = logging.getLogger(__name__)


async def snapshot_org_trends_job(db: AsyncSession, org_id: int) -> None:
    """Capture shared trend snapshots on scheduler cadence."""
    started = datetime.now(UTC)
    try:
        result = await trend_telemetry.snapshot_org_trends(db, org_id)
        details: dict[str, object] = {
            "written": int(result.get("written", 0)),
            "skipped": int(result.get("skipped", 0)),
        }
        await record_job_run(
            db, org_id=org_id, job_name="trend_snapshot", status="ok",
            started_at=started, finished_at=datetime.now(UTC), details=details,
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Trend snapshot failed org=%d category=%s error_type=%s",
            org_id, scheduler_error_category(exc), type(exc).__name__, exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="trend_snapshot", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        await db.commit()


async def snapshot_layer_scores_job(db: AsyncSession, org_id: int) -> None:
    """Snapshot all layer scores for historical trend tracking (daily dedup)."""
    started = datetime.now(UTC)
    try:
        from app.services.layer_snapshots import snapshot_all_layers

        result = await snapshot_all_layers(db, org_id)
        await record_job_run(
            db, org_id=org_id, job_name="layer_snapshot", status="ok",
            started_at=started, finished_at=datetime.now(UTC), details=result,
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Layer snapshot failed org=%d category=%s error_type=%s",
            org_id, scheduler_error_category(exc), type(exc).__name__, exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="layer_snapshot", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        await db.commit()
