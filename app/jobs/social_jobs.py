"""Social media jobs — auto-publish scheduled posts."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import LOG_DETAIL_MAX_CHARS
from app.core.resilience import IntegrationSyncError
from app.jobs._helpers import record_job_run

logger = logging.getLogger(__name__)


async def publish_due_social_posts(db: AsyncSession, org_id: int) -> None:
    from app.logs.audit import record_action
    from app.services import social as social_service

    started = datetime.now(UTC)
    try:
        published = await social_service.publish_due_queued_posts(db, organization_id=org_id)
        if published > 0:
            await record_action(
                db=db, organization_id=org_id, actor_user_id=None,
                event_type="social_posts_auto_published", entity_type="scheduler",
                entity_id=None, payload_json={"count": published, "trigger": "scheduled"},
            )
        await record_job_run(
            db, org_id=org_id, job_name="social_publish_queue", status="ok",
            started_at=started, finished_at=datetime.now(UTC),
            details={"published_count": published},
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError, IntegrationSyncError, TimeoutError, ConnectionError,
        RuntimeError, ValueError, TypeError, OSError, ImportError, AttributeError,
    ) as exc:
        await record_job_run(
            db, org_id=org_id, job_name="social_publish_queue", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:LOG_DETAIL_MAX_CHARS]}",
        )
        await db.commit()
