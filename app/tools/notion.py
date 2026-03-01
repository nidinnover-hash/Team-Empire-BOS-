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

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


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
    """Search Notion workspace for pages/databases with auto-pagination."""
    per_page = min(page_size, 100)
    payload: dict[str, Any] = {"page_size": per_page}
    if query:
        payload["query"] = query
    if filter_type in ("page", "database"):
        payload["filter"] = {"value": filter_type, "property": "object"}
    client = _get_client()
    all_results: list[dict[str, Any]] = []
    while len(all_results) < page_size:
        resp = await client.post(f"{_BASE}/search", json=payload, headers=_headers(token))
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        if isinstance(results, list):
            all_results.extend(results)
        if not body.get("has_more") or not body.get("next_cursor"):
            break
        payload["start_cursor"] = body["next_cursor"]
    return all_results[:page_size]


async def get_page(token: str, page_id: str) -> dict[str, Any]:
    """Retrieve a single Notion page by ID."""
    client = _get_client()
    resp = await client.get(f"{_BASE}/pages/{page_id}", headers=_headers(token))
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def get_page_content(token: str, block_id: str, *, page_size: int = 100) -> list[dict[str, Any]]:
    """Retrieve block children (page content) with auto-pagination."""
    per_page = min(page_size, 100)
    params: dict[str, Any] = {"page_size": per_page}
    client = _get_client()
    all_blocks: list[dict[str, Any]] = []
    while len(all_blocks) < page_size:
        resp = await client.get(
            f"{_BASE}/blocks/{block_id}/children",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        if isinstance(results, list):
            all_blocks.extend(results)
        if not body.get("has_more") or not body.get("next_cursor"):
            break
        params["start_cursor"] = body["next_cursor"]
    return all_blocks[:page_size]


async def query_database(
    token: str,
    database_id: str,
    *,
    page_size: int = 50,
    filter_obj: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Query a Notion database with auto-pagination."""
    per_page = min(page_size, 100)
    payload: dict[str, Any] = {"page_size": per_page}
    if filter_obj:
        payload["filter"] = filter_obj
    client = _get_client()
    all_results: list[dict[str, Any]] = []
    while len(all_results) < page_size:
        resp = await client.post(
            f"{_BASE}/databases/{database_id}/query",
            json=payload,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        if isinstance(results, list):
            all_results.extend(results)
        if not body.get("has_more") or not body.get("next_cursor"):
            break
        payload["start_cursor"] = body["next_cursor"]
    return all_results[:page_size]


async def get_me(token: str) -> dict[str, Any]:
    """Get the bot user info (verifies token)."""
    client = _get_client()
    resp = await client.get(f"{_BASE}/users/me", headers=_headers(token))
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}
