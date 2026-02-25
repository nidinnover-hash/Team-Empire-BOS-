"""LinkedIn integration service — connect, publish, status."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.integration import (
    connect_integration,
    get_integration_by_type,
    mark_sync_time,
)
from app.tools import linkedin as linkedin_tool

logger = logging.getLogger(__name__)
_TYPE = "linkedin"


async def connect_linkedin(
    db: AsyncSession, org_id: int, access_token: str
) -> dict:
    profile = await linkedin_tool.verify_token(access_token)
    name = profile.get("name", profile.get("localizedFirstName", ""))
    sub = profile.get("sub", "")
    author_urn = f"urn:li:person:{sub}" if sub else ""
    integration = await connect_integration(
        db, organization_id=org_id, integration_type=_TYPE,
        config_json={
            "access_token": access_token,
            "name": name,
            "author_urn": author_urn,
        },
    )
    return {
        "id": integration.id,
        "connected": True,
        "name": name,
        "author_urn": author_urn,
    }


async def get_linkedin_status(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False}
    cfg = integration.config_json or {}
    return {
        "connected": True,
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
        "name": cfg.get("name"),
        "author_urn": cfg.get("author_urn"),
    }


async def publish_post(
    db: AsyncSession, org_id: int, text: str, visibility: str = "PUBLIC"
) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("LinkedIn not connected")
    cfg = integration.config_json or {}
    token = cfg.get("access_token", "")
    author_urn = cfg.get("author_urn", "")
    if not author_urn:
        raise ValueError("LinkedIn author URN not found — reconnect")
    result = await linkedin_tool.create_text_post(
        token, author_urn=author_urn, text=text, visibility=visibility,
    )
    await mark_sync_time(db, integration)
    return {"post_id": result.get("id", ""), "status": result.get("status", "published")}
