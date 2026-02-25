"""Notion API — page/database read and sync.

Pure async httpx client, no DB.
Uses Notion API v2022-06-28 (Integration token or OAuth).
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.notion.com/v1"
_TIMEOUT = 20.0
_VERSION = "2022-06-28"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": _VERSION,
    }


async def search_pages(
    token: str,
    query: str = "",
    *,
    page_size: int = 20,
    filter_type: str | None = None,
) -> list[dict[str, Any]]:
    """Search Notion workspace for pages/databases."""
    payload: dict[str, Any] = {"page_size": min(page_size, 100)}
    if query:
        payload["query"] = query
    if filter_type in ("page", "database"):
        payload["filter"] = {"value": filter_type, "property": "object"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{_BASE}/search", json=payload, headers=_headers(token))
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        return results if isinstance(results, list) else []


async def get_page(token: str, page_id: str) -> dict[str, Any]:
    """Retrieve a single Notion page by ID."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/pages/{page_id}", headers=_headers(token))
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, dict) else {}


async def get_page_content(token: str, block_id: str, *, page_size: int = 100) -> list[dict[str, Any]]:
    """Retrieve block children (page content) for a given block/page."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/blocks/{block_id}/children",
            params={"page_size": min(page_size, 100)},
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        return results if isinstance(results, list) else []


async def query_database(
    token: str,
    database_id: str,
    *,
    page_size: int = 50,
    filter_obj: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Query a Notion database and return rows."""
    payload: dict[str, Any] = {"page_size": min(page_size, 100)}
    if filter_obj:
        payload["filter"] = filter_obj
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_BASE}/databases/{database_id}/query",
            json=payload,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        return results if isinstance(results, list) else []


async def get_me(token: str) -> dict[str, Any]:
    """Get the bot user info (verifies token)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/users/me", headers=_headers(token))
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, dict) else {}
