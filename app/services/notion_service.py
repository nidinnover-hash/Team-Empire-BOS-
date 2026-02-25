"""Notion integration service — connect, search, sync pages to notes."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
    mark_sync_time,
)
from app.tools import notion as notion_tool

logger = logging.getLogger(__name__)
_TYPE = "notion"


def _extract_title(page: dict) -> str:
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in title_parts if isinstance(t, dict))
    return page.get("id", "untitled")


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


async def connect_notion(
    db: AsyncSession, org_id: int, api_token: str
) -> dict:
    me = await notion_tool.get_me(api_token)
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
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("Notion not connected")
    token = (integration.config_json or {}).get("api_token", "")
    pages = await notion_tool.search_pages(token, query, page_size=max_pages, filter_type="page")
    # Pre-load existing Notion note titles for dedup
    existing_result = await db.execute(
        select(Note.title).where(
            Note.organization_id == org_id,
            Note.source == "notion",
        ).limit(1000)
    )
    existing_titles = {row.title for row in existing_result}
    notes_created = 0
    for page in pages[:max_pages]:
        title = _extract_title(page)
        page_id = page.get("id", "")
        if not page_id:
            continue
        note_title = f"[Notion] {title}"[:200]
        # Skip if this page was already synced
        if note_title in existing_titles:
            continue
        try:
            blocks = await notion_tool.get_page_content(token, page_id, page_size=50)
            content = _blocks_to_text(blocks)
        except Exception:
            content = ""
        if not content.strip():
            continue
        note = Note(
            organization_id=org_id,
            title=note_title,
            content=content[:6000],
            source="notion",
            created_at=datetime.now(timezone.utc),
        )
        db.add(note)
        notes_created += 1
    if notes_created:
        await db.commit()
    await mark_sync_time(db, integration)
    return {
        "pages_synced": len(pages),
        "notes_created": notes_created,
        "last_sync_at": datetime.now(timezone.utc).isoformat(),
    }


async def search_pages(
    db: AsyncSession, org_id: int, query: str = "", page_size: int = 20
) -> list[dict]:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("Notion not connected")
    token = (integration.config_json or {}).get("api_token", "")
    pages = await notion_tool.search_pages(token, query, page_size=page_size)
    return [
        {"id": p.get("id", ""), "title": _extract_title(p), "url": p.get("url", "")}
        for p in pages
    ]
