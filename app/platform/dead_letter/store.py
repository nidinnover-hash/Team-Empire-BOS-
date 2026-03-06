"""Dead-letter store — writes failed operations into the dead_letter_entries table."""
from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dead_letter import DeadLetterEntry

logger = logging.getLogger(__name__)


async def capture_failure(
    db: AsyncSession,
    *,
    organization_id: int,
    source_type: str,
    source_id: str | None = None,
    source_detail: str | None = None,
    payload: dict[str, Any] | None = None,
    error_message: str | None = None,
    error_type: str | None = None,
    attempts: int = 1,
    max_attempts: int = 3,
) -> DeadLetterEntry | None:
    """Capture a failed operation into the dead-letter queue.

    Returns the created entry, or None if dead-letter is disabled or capture fails.
    Fire-and-forget safe — never raises.
    """
    if not getattr(settings, "DEAD_LETTER_ENABLED", True):
        return None

    try:
        entry = DeadLetterEntry(
            organization_id=organization_id,
            source_type=source_type[:30],
            source_id=str(source_id)[:100] if source_id is not None else None,
            source_detail=str(source_detail)[:200] if source_detail is not None else None,
            payload=payload or {},
            error_message=str(error_message)[:2000] if error_message else None,
            error_type=str(error_type)[:100] if error_type else None,
            attempts=attempts,
            max_attempts=max_attempts,
            status="pending",
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        logger.info(
            "Dead-letter captured: org=%d source=%s/%s error_type=%s",
            organization_id, source_type, source_id, error_type,
        )
        return entry
    except Exception:
        logger.debug("Dead-letter capture failed", exc_info=True)
        with suppress(Exception):
            await db.rollback()
        return None
