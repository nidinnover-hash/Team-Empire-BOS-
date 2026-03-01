"""HubSpot CRM integration service — connect, sync contacts/deals."""
from __future__ import annotations

import logging
from collections.abc import Hashable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import run_with_retry
from app.db.base import Base as ORMBase
from app.models.contact import Contact
from app.models.note import Note
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
)
from app.services.sync_base import IntegrationSync
from app.tools import hubspot as hubspot_tool

logger = logging.getLogger(__name__)
_TYPE = "hubspot"


# ---------------------------------------------------------------------------
# Sync subclass
# ---------------------------------------------------------------------------

class HubSpotSync(IntegrationSync):
    """Sync HubSpot contacts → Contact model."""

    provider = "hubspot"

    async def fetch_items(self, token: str, config: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
        return await hubspot_tool.list_contacts(
            token, limit=100,
            properties=["firstname", "lastname", "email", "company", "phone", "lifecyclestage"],
        )

    async def load_existing_keys(self, db: AsyncSession, org_id: int) -> set[Hashable]:
        result = await db.execute(
            select(Contact.email).where(
                Contact.organization_id == org_id,
                Contact.email.isnot(None),
            ).limit(5000)
        )
        return {row.email.lower() for row in result if row.email}

    def dedup_key(self, item: dict[str, Any]) -> Hashable:
        email = (item.get("properties", {}).get("email") or "").strip()
        if not email:
            raise ValueError("contact has no email")
        return email.lower()

    def to_model(self, item: dict[str, Any], org_id: int) -> ORMBase:
        props = item.get("properties", {})
        email = (props.get("email") or "").strip()
        first = props.get("firstname", "")
        last = props.get("lastname", "")
        name = f"{first} {last}".strip() or email
        company = props.get("company", "")
        phone = props.get("phone", "")
        return Contact(
            organization_id=org_id,
            name=name[:100],
            email=email[:200],
            phone=phone[:50] if phone else None,
            company=company[:200] if company else None,
            relationship="business",
            notes=f"Synced from HubSpot (lifecycle: {props.get('lifecyclestage', 'unknown')})",
            created_at=datetime.now(UTC),
        )


class HubSpotDealSync(IntegrationSync):
    """Sync HubSpot deals → Note model (source='hubspot_deal')."""

    provider = "hubspot"

    async def fetch_items(self, token: str, config: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
        return await hubspot_tool.list_deals(
            token, limit=100,
            properties=["dealname", "amount", "dealstage", "closedate"],
        )

    async def load_existing_keys(self, db: AsyncSession, org_id: int) -> set[Hashable]:
        result = await db.execute(
            select(Note.title).where(
                Note.organization_id == org_id,
                Note.source == "hubspot_deal",
            ).limit(5000)
        )
        return {row.title for row in result if row.title}

    def dedup_key(self, item: dict[str, Any]) -> Hashable:
        props = item.get("properties", {})
        name = (props.get("dealname") or "").strip()
        if not name:
            raise ValueError("deal has no name")
        return f"[HubSpot Deal] {name}"[:200]

    def to_model(self, item: dict[str, Any], org_id: int) -> ORMBase:
        props = item.get("properties", {})
        name = (props.get("dealname") or "Unnamed Deal").strip()
        amount = props.get("amount", "")
        stage = props.get("dealstage", "unknown")
        close_date = props.get("closedate", "")
        content_parts = [f"Deal: {name}", f"Stage: {stage}"]
        if amount:
            content_parts.append(f"Amount: {amount}")
        if close_date:
            content_parts.append(f"Close date: {close_date}")
        return Note(
            organization_id=org_id,
            title=f"[HubSpot Deal] {name}"[:200],
            content="\n".join(content_parts)[:6000],
            source="hubspot_deal",
            created_at=datetime.now(UTC),
        )


_hubspot_sync = HubSpotSync()
_hubspot_deal_sync = HubSpotDealSync()


# ---------------------------------------------------------------------------
# Public API (unchanged signatures for backward compat)
# ---------------------------------------------------------------------------

async def connect_hubspot(
    db: AsyncSession, org_id: int, access_token: str
) -> dict:
    await run_with_retry(lambda: hubspot_tool.get_owner(access_token))
    integration = await connect_integration(
        db, organization_id=org_id, integration_type=_TYPE,
        config_json={"access_token": access_token},
    )
    return {"id": integration.id, "connected": True}


async def get_hubspot_status(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False}
    return {
        "connected": True,
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
    }


async def sync_hubspot_data(
    db: AsyncSession, org_id: int
) -> dict:
    contact_result = await _hubspot_sync.sync(db, org_id)

    # Deals: persist to Note(source='hubspot_deal')
    deals_synced = 0
    try:
        deal_result = await _hubspot_deal_sync.sync(db, org_id)
        deals_synced = deal_result.synced
    except Exception:
        logger.warning("HubSpot deals sync failed for org %d", org_id, exc_info=True)

    return {
        "contacts_synced": contact_result.synced,
        "deals_synced": deals_synced,
        "last_sync_at": contact_result.last_sync_at.isoformat(),
    }
