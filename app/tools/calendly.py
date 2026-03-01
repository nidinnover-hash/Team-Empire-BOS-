"""Calendly API v2 — scheduled events and availability.

Pure async httpx client, no DB.
Uses Calendly API v2 with Personal Access Token or OAuth.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.calendly.com"
_TIMEOUT = 20.0

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
    }


async def get_current_user(token: str) -> dict[str, Any]:
    """Get the authenticated user's profile and org URI."""
    client = _get_client()
    resp = await client.get(f"{_BASE}/users/me", headers=_headers(token))
    resp.raise_for_status()
    body = resp.json()
    resource = body.get("resource", {})
    return resource if isinstance(resource, dict) else {}


async def list_scheduled_events(
    token: str,
    user_uri: str,
    *,
    min_start_time: str | None = None,
    max_start_time: str | None = None,
    count: int = 25,
    status: str = "active",
) -> list[dict[str, Any]]:
    """List scheduled events for the user with auto-pagination."""
    page_size = min(count, 100)
    params: dict[str, Any] = {
        "user": user_uri,
        "count": page_size,
        "status": status,
    }
    if min_start_time:
        params["min_start_time"] = min_start_time
    if max_start_time:
        params["max_start_time"] = max_start_time
    client = _get_client()
    all_events: list[dict[str, Any]] = []
    while len(all_events) < count:
        resp = await client.get(
            f"{_BASE}/scheduled_events",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        collection = body.get("collection", [])
        if isinstance(collection, list):
            all_events.extend(collection)
        next_token = (body.get("pagination") or {}).get("next_page_token")
        if not next_token:
            break
        params["page_token"] = next_token
    return all_events[:count]


async def get_event(token: str, event_uuid: str) -> dict[str, Any]:
    """Get a single scheduled event by UUID."""
    client = _get_client()
    resp = await client.get(
        f"{_BASE}/scheduled_events/{event_uuid}",
        headers=_headers(token),
    )
    resp.raise_for_status()
    body = resp.json()
    resource = body.get("resource", {})
    return resource if isinstance(resource, dict) else {}


async def list_event_invitees(
    token: str,
    event_uuid: str,
    *,
    count: int = 25,
) -> list[dict[str, Any]]:
    """List invitees for a scheduled event with auto-pagination."""
    page_size = min(count, 100)
    params: dict[str, Any] = {"count": page_size}
    client = _get_client()
    all_invitees: list[dict[str, Any]] = []
    while len(all_invitees) < count:
        resp = await client.get(
            f"{_BASE}/scheduled_events/{event_uuid}/invitees",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        collection = body.get("collection", [])
        if isinstance(collection, list):
            all_invitees.extend(collection)
        next_token = (body.get("pagination") or {}).get("next_page_token")
        if not next_token:
            break
        params["page_token"] = next_token
    return all_invitees[:count]


async def list_event_types(
    token: str,
    user_uri: str,
    *,
    count: int = 25,
    active: bool = True,
) -> list[dict[str, Any]]:
    """List event types (booking page types) for the user with auto-pagination."""
    page_size = min(count, 100)
    params: dict[str, Any] = {
        "user": user_uri,
        "count": page_size,
    }
    if active:
        params["active"] = "true"
    client = _get_client()
    all_types: list[dict[str, Any]] = []
    while len(all_types) < count:
        resp = await client.get(
            f"{_BASE}/event_types",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        collection = body.get("collection", [])
        if isinstance(collection, list):
            all_types.extend(collection)
        next_token = (body.get("pagination") or {}).get("next_page_token")
        if not next_token:
            break
        params["page_token"] = next_token
    return all_types[:count]
