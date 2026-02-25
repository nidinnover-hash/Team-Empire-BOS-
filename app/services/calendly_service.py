"""Calendly integration service — connect, sync events to daily context."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import DailyContext
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
    mark_sync_time,
)
from app.tools import calendly as calendly_tool

logger = logging.getLogger(__name__)
_TYPE = "calendly"


async def connect_calendly(
    db: AsyncSession, org_id: int, api_token: str
) -> dict:
    user = await calendly_tool.get_current_user(api_token)
    user_name = user.get("name", "")
    user_uri = user.get("uri", "")
    integration = await connect_integration(
        db, organization_id=org_id, integration_type=_TYPE,
        config_json={
            "api_token": api_token,
            "user_name": user_name,
            "user_uri": user_uri,
        },
    )
    return {"id": integration.id, "connected": True, "user_name": user_name}


async def get_calendly_status(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False}
    cfg = integration.config_json or {}
    return {
        "connected": True,
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
        "user_name": cfg.get("user_name"),
    }


async def sync_events(
    db: AsyncSession, org_id: int, *, days_ahead: int = 7
) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("Calendly not connected")
    cfg = integration.config_json or {}
    token = cfg.get("api_token", "")
    user_uri = cfg.get("user_uri", "")
    if not user_uri:
        raise ValueError("Calendly user URI missing — reconnect")
    now = datetime.now(timezone.utc)
    max_time = now + timedelta(days=days_ahead)
    events = await calendly_tool.list_scheduled_events(
        token, user_uri,
        min_start_time=now.isoformat(),
        max_start_time=max_time.isoformat(),
        count=50,
    )
    synced = 0
    for event in events:
        name = event.get("name", "Calendly Meeting")
        start = event.get("start_time", "")
        end = event.get("end_time", "")
        location_data = event.get("location", {})
        location = ""
        if isinstance(location_data, dict):
            location = location_data.get("join_url", "") or location_data.get("location", "")
        event_date = date.today()
        if start:
            try:
                event_date = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
            except (ValueError, TypeError):
                pass
        content = f"[Calendly] {name}"
        if start:
            content += f" | {start}"
        if location:
            content += f" | {location}"
        ctx = DailyContext(
            organization_id=org_id,
            date=event_date,
            context_type="calendly_event",
            content=content[:2000],
            related_to=name[:100],
            created_at=datetime.now(timezone.utc),
        )
        db.add(ctx)
        synced += 1
    if synced:
        await db.commit()
    await mark_sync_time(db, integration)
    upcoming = len([e for e in events if e.get("status") == "active"])
    return {
        "events_synced": synced,
        "upcoming_events": upcoming,
        "last_sync_at": datetime.now(timezone.utc).isoformat(),
    }
