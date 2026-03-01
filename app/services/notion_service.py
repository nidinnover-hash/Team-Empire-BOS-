"""Notion integration service — connect, search, sync pages to notes."""
from __future__ import annotations

import logging
from collections.abc import Hashable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import run_with_retry
from app.db.base import Base as ORMBase
from app.models.note import Note
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
)
from app.services.sync_base import IntegrationSync
from app.tools import notion as notion_tool

logger = logging.getLogger(__name__)
_TYPE = "notion"


def _extract_title(page: dict) -> str:
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in title_parts if isinstance(t, dict))
    page_id = page.get("id")
    return str(page_id) if page_id else "untitled"


def _blocks_to_text(blocks: list[dict]) -> str:
    lines: list[str] = []
    for block in blocks:
        btype = block.get("type", "")
        data = block.get(btype, {})
        rich_text = data.get("rich_text", [])
        if isinstance(rich_text, list):
            text = "".join(t.get("plain_text", "") for t in rich_text if isinstance(t, dict))
            if text.strip():
                lines.append(text.strip())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sync subclass
# ---------------------------------------------------------------------------

class NotionSync(IntegrationSync):
    """Sync Notion pages → Note model."""

    provider = "notion"

    def __init__(self) -> None:
        self._token: str = ""

    def _token_field(self) -> str:
        return "api_token"

    async def fetch_items(self, token: str, config: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
        self._token = token
        query = kwargs.get("query", "")
        max_pages = kwargs.get("max_pages", 20)
        pages = await notion_tool.search_pages(token, query, page_size=max_pages, filter_type="page")
        # Enrich each page with content blocks
        enriched: list[dict[str, Any]] = []
        for page in pages[:max_pages]:
            page_id = page.get("id", "")
            if not page_id:
                continue
            title = _extract_title(page)
            try:
                async def _get_page_content(pid: str = page_id) -> list[dict[str, Any]]:
                    return await notion_tool.get_page_content(token, pid, page_size=50)

                blocks = await run_with_retry(
                    _get_page_content,
                )
                content = _blocks_to_text(blocks)
            except (RuntimeError, ValueError, TypeError, TimeoutError):
                logger.warning("Failed to fetch Notion page %s", page_id, exc_info=True)
                content = ""
            if not content.strip():
                continue
            enriched.append({"title": title, "content": content, "page_id": page_id})
        return enriched

    async def load_existing_keys(self, db: AsyncSession, org_id: int) -> set[Hashable]:
        result = await db.execute(
            select(Note.title).where(
                Note.organization_id == org_id,
                Note.source == "notion",
            ).limit(1000)
        )
        return {row.title for row in result}

    def dedup_key(self, item: dict[str, Any]) -> Hashable:
        return f"[Notion] {item['title']}"[:200]

    def to_model(self, item: dict[str, Any], org_id: int) -> ORMBase:
        return Note(
            organization_id=org_id,
            title=f"[Notion] {item['title']}"[:200],
            content=item["content"][:6000],
            source="notion",
            created_at=datetime.now(UTC),
        )


_notion_sync = NotionSync()


# ---------------------------------------------------------------------------
# Public API (unchanged signatures for backward compat)
# ---------------------------------------------------------------------------

async def connect_notion(
    db: AsyncSession, org_id: int, api_token: str
) -> dict:
    me = await run_with_retry(lambda: notion_tool.get_me(api_token))
    bot_name = me.get("name", "Notion Bot")
    integration = await connect_integration(
        db, organization_id=org_id, integration_type=_TYPE,
        config_json={"api_token": api_token, "bot_name": bot_name},
    )
    return {"id": integration.id, "connected": True, "bot_name": bot_name}


async def get_notion_status(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False}
    cfg = integration.config_json or {}
    return {
        "connected": True,
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
        "bot_name": cfg.get("bot_name"),
    }


async def sync_pages_to_notes(
    db: AsyncSession, org_id: int, *, query: str = "", max_pages: int = 20
) -> dict:
    result = await _notion_sync.sync(db, org_id, query=query, max_pages=max_pages)
    return {
        "pages_synced": result.synced + result.skipped,
        "notes_created": result.synced,
        "last_sync_at": result.last_sync_at.isoformat(),
    }


async def search_pages(
    db: AsyncSession, org_id: int, query: str = "", page_size: int = 20
) -> list[dict]:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("Notion not connected")
    token = (integration.config_json or {}).get("api_token", "")
    pages = await run_with_retry(lambda: notion_tool.search_pages(token, query, page_size=page_size))
    return [
        {"id": p.get("id", ""), "title": _extract_title(p), "url": p.get("url", "")}
        for p in pages
    ]
