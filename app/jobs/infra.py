"""Infrastructure jobs — backups and webhook retry."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs._helpers import scheduler_error_category

logger = logging.getLogger(__name__)

_last_backup_date: str | None = None


async def maybe_run_daily_backup() -> None:
    """Run DB backup once per calendar day."""
    global _last_backup_date
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if _last_backup_date == today:
        return
    try:
        from app.services.db_backup import create_backup
        result = await create_backup()
        if result.get("ok"):
            _last_backup_date = today
            logger.info("Daily backup completed: %s", result.get("file"))
        else:
            logger.warning("Daily backup failed: %s", result.get("error"))
    except Exception as exc:
        logger.warning(
            "Daily backup failed category=%s error_type=%s",
            scheduler_error_category(exc), type(exc).__name__, exc_info=True,
        )


async def retry_webhook_deliveries(db: AsyncSession) -> None:
    """Retry failed webhook deliveries whose next_retry_at has passed."""
    try:
        from app.services.webhook import retry_failed_deliveries
        retried = await retry_failed_deliveries(db)
        if retried:
            logger.info("Retried %d failed webhook deliveries", retried)
    except Exception as exc:
        logger.warning(
            "Webhook retry failed category=%s error_type=%s",
            scheduler_error_category(exc), type(exc).__name__, exc_info=True,
        )
