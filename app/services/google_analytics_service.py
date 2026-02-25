"""Google Analytics 4 integration service — connect via OAuth, sync metrics."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
    mark_sync_time,
)
from app.tools import google_analytics as ga_tool

logger = logging.getLogger(__name__)
_TYPE = "google_analytics"


async def connect_google_analytics(
    db: AsyncSession, org_id: int, access_token: str, property_id: str | None = None
) -> dict:
    pid = property_id or settings.GA4_PROPERTY_ID or ""
    if not pid:
        raise ValueError("GA4_PROPERTY_ID must be set in config or provided")
    integration = await connect_integration(
        db, organization_id=org_id, integration_type=_TYPE,
        config_json={"access_token": access_token, "property_id": pid},
    )
    return {"id": integration.id, "connected": True, "property_id": pid}


async def get_ga_status(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False}
    cfg = integration.config_json or {}
    return {
        "connected": True,
        "property_id": cfg.get("property_id"),
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
    }


async def sync_analytics(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("Google Analytics not connected")
    cfg = integration.config_json or {}
    token = cfg.get("access_token", "")
    pid = cfg.get("property_id", "")
    report = await ga_tool.run_report(token, pid)
    rows = report.get("rows", [])
    sessions = 0
    users = 0
    views = 0
    for row in rows:
        vals = row.get("metricValues", [])
        if len(vals) >= 3:
            sessions += int(vals[0].get("value", 0))
            users += int(vals[1].get("value", 0))
            views += int(vals[2].get("value", 0))
    sources_report = await ga_tool.get_traffic_sources(token, pid)
    sources = []
    for row in (sources_report.get("rows", []))[:10]:
        dims = row.get("dimensionValues", [])
        vals = row.get("metricValues", [])
        if dims:
            sources.append({
                "source": dims[0].get("value", ""),
                "medium": dims[1].get("value", "") if len(dims) > 1 else "",
                "sessions": vals[0].get("value", "0") if vals else "0",
            })
    pages_report = await ga_tool.get_top_pages(token, pid)
    top_pages = []
    for row in (pages_report.get("rows", []))[:10]:
        dims = row.get("dimensionValues", [])
        vals = row.get("metricValues", [])
        if dims:
            top_pages.append({
                "page": dims[0].get("value", ""),
                "views": vals[0].get("value", "0") if vals else "0",
            })
    await mark_sync_time(db, integration)
    return {
        "sessions_30d": sessions,
        "active_users_30d": users,
        "page_views_30d": views,
        "top_pages": top_pages,
        "traffic_sources": sources,
    }
