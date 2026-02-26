"""HubSpot CRM integration service — connect, sync contacts/deals."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
    mark_sync_time,
)
from app.tools import hubspot as hubspot_tool

logger = logging.getLogger(__name__)
_TYPE = "hubspot"


async def connect_hubspot(
    db: AsyncSession, org_id: int, access_token: str
) -> dict:
    await hubspot_tool.get_owner(access_token)
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
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("HubSpot not connected")
    token = (integration.config_json or {}).get("access_token", "")
    contacts = await hubspot_tool.list_contacts(
        token, limit=100,
        properties=["firstname", "lastname", "email", "company", "phone", "lifecyclestage"],
    )
    contacts_synced = 0
    for c in contacts:
        props = c.get("properties", {})
        email = (props.get("email") or "").strip()
        if not email:
            continue
        first = props.get("firstname", "")
        last = props.get("lastname", "")
        name = f"{first} {last}".strip() or email
        company = props.get("company", "")
        phone = props.get("phone", "")
        contact = Contact(
            organization_id=org_id,
            name=name[:100],
            email=email[:200],
            phone=phone[:50] if phone else None,
            company=company[:200] if company else None,
            relationship="business",
            notes=f"Synced from HubSpot (lifecycle: {props.get('lifecyclestage', 'unknown')})",
            created_at=datetime.now(UTC),
        )
        db.add(contact)
        contacts_synced += 1
    deals = await hubspot_tool.list_deals(
        token, limit=100,
        properties=["dealname", "amount", "dealstage", "closedate"],
    )
    if contacts_synced or deals:
        await db.commit()
    await mark_sync_time(db, integration)
    return {
        "contacts_synced": contacts_synced,
        "deals_synced": len(deals),
        "last_sync_at": datetime.now(UTC).isoformat(),
    }
