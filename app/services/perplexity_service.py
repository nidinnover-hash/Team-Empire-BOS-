"""Perplexity integration service — connect, search, news digest."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.integration import (
    connect_integration,
    get_integration_by_type,
    mark_sync_time,
)
from app.tools import perplexity as perplexity_tool

logger = logging.getLogger(__name__)
_TYPE = "perplexity"


async def connect_perplexity(
    db: AsyncSession, org_id: int, api_key: str
) -> dict:
    ok = await perplexity_tool.verify_key(api_key)
    if not ok:
        raise ValueError("Invalid Perplexity API key")
    integration = await connect_integration(
        db, organization_id=org_id, integration_type=_TYPE,
        config_json={"api_key": api_key},
    )
    return {"id": integration.id, "connected": True}


async def get_perplexity_status(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False}
    return {
        "connected": True,
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
    }


async def search_web(
    db: AsyncSession, org_id: int, query: str, max_tokens: int = 1024
) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("Perplexity not connected")
    api_key = (integration.config_json or {}).get("api_key", "")
    result = await perplexity_tool.search(api_key, query, max_tokens=max_tokens)
    await mark_sync_time(db, integration)
    content = ""
    citations: list[str] = []
    choices = result.get("choices", [])
    if choices:
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
    raw_citations = result.get("citations", [])
    if isinstance(raw_citations, list):
        citations = [str(c) for c in raw_citations]
    return {"content": content, "citations": citations}


async def search_news(
    db: AsyncSession, org_id: int, topics: list[str], max_items: int = 10
) -> list[dict]:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("Perplexity not connected")
    api_key = (integration.config_json or {}).get("api_key", "")
    results = await perplexity_tool.search_news(api_key, topics, max_items=max_items)
    await mark_sync_time(db, integration)
    return results
