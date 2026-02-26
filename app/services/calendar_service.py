"""
Calendar service — sync Google Calendar events into DailyContext.

Events are stored as context_type="calendar_event" entries so they automatically
appear in the daily briefing and AI memory context without any schema changes.
"""
import logging
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.resilience import run_with_retry
from app.models.memory import DailyContext
from app.services.integration import get_integration_by_type, mark_sync_time
from app.tools.google_calendar import list_events_for_day, refresh_access_token

logger = logging.getLogger(__name__)


def _format_event_time(dt_str: str | None) -> str:
    """Parse ISO datetime string to readable time like '9:00 AM'."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        hour = dt.hour
        minute = dt.minute
        period = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        return f"{display_hour}:{minute:02d} {period}"
    except ValueError:
        return dt_str[:10] if dt_str else ""


def _event_to_content(event: dict) -> str:
    """Build a readable content string from a Google Calendar event dict."""
    title = event.get("summary", "Untitled Event")
    start_obj = event.get("start", {})
    end_obj = event.get("end", {})

    # All-day events use "date", timed events use "dateTime"
    if "dateTime" in start_obj:
        start_str = _format_event_time(start_obj["dateTime"])
        end_str = _format_event_time(end_obj.get("dateTime"))
        return f"{title} ({start_str} - {end_str})"
    else:
        return f"{title} (all day)"


async def sync_calendar_events(
    db: AsyncSession,
    organization_id: int,
    target_date: date | None = None,
) -> dict:
    """
    Fetch today's (or target_date's) Google Calendar events and store them
    as DailyContext entries with context_type='calendar_event'.

    Returns:
        {"synced": int, "date": str, "error": str | None}
    """
    target = target_date or date.today()

    integration = await get_integration_by_type(db, organization_id, "google_calendar")
    if integration is None or integration.status != "connected":
        return {"synced": 0, "date": str(target), "error": "Google Calendar not connected"}

    access_token = integration.config_json.get("access_token")
    refresh_token = integration.config_json.get("refresh_token")
    calendar_id = integration.config_json.get("calendar_id", "primary")

    if not access_token:
        return {"synced": 0, "date": str(target), "error": "Missing access_token"}

    # Fetch events, auto-refresh token on failure
    events = None
    try:
        events = await run_with_retry(
            lambda: list_events_for_day(access_token, target, calendar_id),
            attempts=2,
            timeout_seconds=25.0,
            retry_exceptions=(httpx.HTTPError, TimeoutError),
        )
    except (httpx.HTTPError, TimeoutError) as exc:
        logger.warning("Calendar fetch failed (%s), trying token refresh", type(exc).__name__)
        if refresh_token and settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
            try:
                refreshed = await run_with_retry(
                    lambda: refresh_access_token(
                        refresh_token=refresh_token,
                        client_id=settings.GOOGLE_CLIENT_ID,
                        client_secret=settings.GOOGLE_CLIENT_SECRET,
                    ),
                    attempts=2,
                    timeout_seconds=25.0,
                    retry_exceptions=(httpx.HTTPError, TimeoutError),
                )
                new_token = refreshed.get("access_token")
                if not new_token:
                    return {"synced": 0, "date": str(target), "error": "Token refresh returned no access_token"}
                # Persist refreshed token — db.add() ensures the reassigned dict is tracked
                integration.config_json = {**integration.config_json, "access_token": new_token}
                db.add(integration)
                await mark_sync_time(db, integration)
                events = await run_with_retry(
                    lambda: list_events_for_day(new_token, target, calendar_id),
                    attempts=2,
                    timeout_seconds=25.0,
                    retry_exceptions=(httpx.HTTPError, TimeoutError),
                )
            except (httpx.HTTPError, TimeoutError):
                return {"synced": 0, "date": str(target), "error": "Token refresh failed or provider unavailable"}
        else:
            return {"synced": 0, "date": str(target), "error": "Calendar provider unavailable or timed out"}

    if events is None:
        return {"synced": 0, "date": str(target), "error": "No events returned"}

    # Delete existing calendar_event entries for this date to avoid duplicates
    await db.execute(
        delete(DailyContext).where(
            DailyContext.organization_id == organization_id,
            DailyContext.date == target,
            DailyContext.context_type == "calendar_event",
        )
    )

    # Insert fresh entries
    now = datetime.now(UTC)
    for event in events:
        content = _event_to_content(event)
        location = event.get("location", "")
        entry = DailyContext(
            organization_id=organization_id,
            date=target,
            context_type="calendar_event",
            content=content,
            related_to=location[:100] if location else None,
            created_at=now,
        )
        db.add(entry)

    await db.commit()
    await mark_sync_time(db, integration)

    logger.info("Synced %d calendar events for org=%s date=%s", len(events), organization_id, target)
    return {"synced": len(events), "date": str(target), "error": None}


async def get_calendar_events_from_context(
    db: AsyncSession,
    organization_id: int,
    for_date: date | None = None,
) -> list[DailyContext]:
    """Return stored calendar events for a date (from DailyContext)."""
    target = for_date or date.today()
    result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == organization_id,
            DailyContext.date == target,
            DailyContext.context_type == "calendar_event",
        ).order_by(DailyContext.created_at).limit(500)
    )
    return list(result.scalars().all())
