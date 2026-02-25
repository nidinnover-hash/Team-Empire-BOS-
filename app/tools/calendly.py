"""Calendly API v2 — scheduled events and availability.

Pure async httpx client, no DB.
Uses Calendly API v2 with Personal Access Token or OAuth.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.calendly.com"
_TIMEOUT = 20.0


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def get_current_user(token: str) -> dict[str, Any]:
    """Get the authenticated user's profile and org URI."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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
    """List scheduled events for the user."""
    params: dict[str, Any] = {
        "user": user_uri,
        "count": min(count, 100),
        "status": status,
    }
    if min_start_time:
        params["min_start_time"] = min_start_time
    if max_start_time:
        params["max_start_time"] = max_start_time
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/scheduled_events",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        collection = body.get("collection", [])
        return collection if isinstance(collection, list) else []


async def get_event(token: str, event_uuid: str) -> dict[str, Any]:
    """Get a single scheduled event by UUID."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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
    """List invitees for a scheduled event."""
    params = {"count": min(count, 100)}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/scheduled_events/{event_uuid}/invitees",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        collection = body.get("collection", [])
        return collection if isinstance(collection, list) else []


async def list_event_types(
    token: str,
    user_uri: str,
    *,
    count: int = 25,
    active: bool = True,
) -> list[dict[str, Any]]:
    """List event types (booking page types) for the user."""
    params: dict[str, Any] = {
        "user": user_uri,
        "count": min(count, 100),
    }
    if active:
        params["active"] = "true"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/event_types",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        collection = body.get("collection", [])
        return collection if isinstance(collection, list) else []
