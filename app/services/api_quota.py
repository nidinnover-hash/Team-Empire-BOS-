from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.trend_telemetry_counter import TrendTelemetryCounter


def _daily_metric_name(day: date) -> str:
    return f"api_requests_day:{day.isoformat()}"


async def consume_api_request_quota(
    db: AsyncSession,
    *,
    organization_id: int,
) -> tuple[bool, int, int]:
    """Consume one API request from the org daily quota.

    Returns (allowed, used_after_attempt, limit).
    """
    limit = int(settings.API_KEY_REQUESTS_PER_DAY)
    if not settings.API_KEY_QUOTA_ENABLED:
        return True, 0, limit

    metric_name = _daily_metric_name(datetime.now(UTC).date())

    async def _attempt_once() -> tuple[bool, int, int]:
        row = (
            (
                await db.execute(
                    select(TrendTelemetryCounter).where(
                        TrendTelemetryCounter.organization_id == int(organization_id),
                        TrendTelemetryCounter.metric_name == metric_name,
                    )
                )
            )
            .scalars()
            .first()
        )
        used_now = int(float(row.metric_value or 0.0)) if row is not None else 0
        if used_now >= limit:
            return False, used_now, limit

        if row is None:
            row = TrendTelemetryCounter(
                organization_id=int(organization_id),
                metric_name=metric_name,
                metric_value=1.0,
                updated_at=datetime.now(UTC),
            )
            db.add(row)
            used_after = 1
        else:
            row.metric_value = float(used_now + 1)
            row.updated_at = datetime.now(UTC)
            used_after = used_now + 1

        await db.commit()
        return True, used_after, limit

    try:
        return await _attempt_once()
    except IntegrityError:
        # Handle concurrent first-write on unique metric row.
        await db.rollback()
        return await _attempt_once()
    except SQLAlchemyError:
        await db.rollback()
        raise
