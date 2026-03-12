"""Calendly integration service — connect, sync events to daily context."""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Hashable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import run_with_retry
from app.db.base import Base as ORMBase
from app.models.memory import DailyContext
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
)
from app.services.sync_base import IntegrationSync
from app.tools import calendly as calendly_tool

logger = logging.getLogger(__name__)
_TYPE = "calendly"


# ---------------------------------------------------------------------------
# Sync subclass
# ---------------------------------------------------------------------------

class CalendlySync(IntegrationSync):
    """Sync Calendly events → DailyContext model."""

    provider = "calendly"

    def _token_field(self) -> str:
        return "api_token"

    async def fetch_items(self, token: str, config: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
        user_uri = config.get("user_uri", "")
        if not user_uri:
            raise ValueError("Calendly user URI missing — reconnect")
        days_ahead = kwargs.get("days_ahead", 7)
        now = datetime.now(UTC)
        max_time = now + timedelta(days=days_ahead)
        return await calendly_tool.list_scheduled_events(
            token, user_uri,
            min_start_time=now.isoformat(),
            max_start_time=max_time.isoformat(),
            count=50,
        )

    async def load_existing_keys(self, db: AsyncSession, org_id: int) -> set[Hashable]:
        result = await db.execute(
            select(DailyContext.related_to, DailyContext.date).where(
                DailyContext.organization_id == org_id,
                DailyContext.context_type == "calendly_event",
            ).limit(500)
        )
        return {(row.related_to, row.date) for row in result}

    def dedup_key(self, item: dict[str, Any]) -> Hashable:
        name = item.get("name", "Calendly Meeting")
        start = item.get("start_time", "")
        event_date = datetime.now(UTC).date()
        if start:
            with contextlib.suppress(ValueError, TypeError):
                event_date = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
        # Stash parsed date on item for to_model() to reuse
        item["_parsed_date"] = event_date
        return (name[:100], event_date)

    def to_model(self, item: dict[str, Any], org_id: int) -> ORMBase:
        name = item.get("name", "Calendly Meeting")
        start = item.get("start_time", "")
        event_date: date = item.get("_parsed_date", datetime.now(UTC).date())

        location_data = item.get("location", {})
        location = ""
        if isinstance(location_data, dict):
            location = location_data.get("join_url", "") or location_data.get("location", "")

        content = f"[Calendly] {name}"
        if start:
            content += f" | {start}"
        if location:
            content += f" | {location}"

        return DailyContext(
            organization_id=org_id,
            date=event_date,
            context_type="calendly_event",
            content=content[:2000],
            related_to=name[:100],
            created_at=datetime.now(UTC),
        )


_calendly_sync = CalendlySync()


# ---------------------------------------------------------------------------
# Public API (unchanged signatures for backward compat)
# ---------------------------------------------------------------------------

async def connect_calendly(
    db: AsyncSession, org_id: int, api_token: str
) -> dict:
    user = await run_with_retry(lambda: calendly_tool.get_current_user(api_token))
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
    result = await _calendly_sync.sync(db, org_id, days_ahead=days_ahead)

    # Link attendees to contacts
    contacts_linked = 0
    try:
        contacts_linked = await _link_attendees_to_contacts(db, org_id)
    except Exception:
        logger.warning("Calendly attendee linking failed for org %d", org_id, exc_info=True)

    return {
        "events_synced": result.synced,
        "upcoming_events": result.synced + result.skipped,
        "contacts_linked": contacts_linked,
        "last_sync_at": result.last_sync_at.isoformat(),
    }


async def _link_attendees_to_contacts(
    db: AsyncSession, org_id: int,
) -> int:
    """Fetch invitees for recent Calendly events and link to contacts via email.

    Updates contact.last_contacted_at and sets next_follow_up_at if not already set.
    """
    from app.models.contact import Contact

    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return 0
    config = integration.config_json or {}
    token = config.get("api_token", "")
    user_uri = config.get("user_uri", "")
    if not token or not user_uri:
        return 0

    # Fetch upcoming events
    now = datetime.now(UTC)
    events = await calendly_tool.list_scheduled_events(
        token, user_uri,
        min_start_time=now.isoformat(),
        max_start_time=(now + timedelta(days=7)).isoformat(),
        count=20,
    )

    linked = 0
    for event in events:
        event_uri = event.get("uri", "")
        if not event_uri:
            continue
        try:
            invitees = await calendly_tool.list_event_invitees(token, event_uri, count=10)
        except Exception:
            logger.debug("Skipping event invitees due to error", exc_info=True)
            continue

        for inv in invitees:
            email = (inv.get("email") or "").strip().lower()
            if not email:
                continue
            result = await db.execute(
                select(Contact).where(
                    Contact.organization_id == org_id,
                    Contact.email == email,
                ).limit(1)
            )
            contact = result.scalar_one_or_none()
            if contact:
                contact.last_contacted_at = now
                if not contact.next_follow_up_at:
                    contact.next_follow_up_at = now + timedelta(days=1)
                linked += 1

    if linked > 0:
        await db.commit()
    return linked
