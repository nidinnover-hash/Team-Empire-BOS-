"""HubSpot CRM API — contacts, deals, and pipeline data.

Pure async httpx client, no DB.
Uses HubSpot API v3 with Private App access token.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.hubapi.com"
_TIMEOUT = 20.0


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def list_contacts(
    token: str,
    *,
    limit: int = 50,
    properties: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List CRM contacts."""
    params: dict[str, Any] = {"limit": min(limit, 100)}
    if properties:
        params["properties"] = ",".join(properties)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/crm/v3/objects/contacts",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        return results if isinstance(results, list) else []


async def list_deals(
    token: str,
    *,
    limit: int = 50,
    properties: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List CRM deals."""
    params: dict[str, Any] = {"limit": min(limit, 100)}
    if properties:
        params["properties"] = ",".join(properties)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/crm/v3/objects/deals",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        return results if isinstance(results, list) else []


async def get_deal_pipeline(
    token: str,
    pipeline_id: str = "default",
) -> dict[str, Any]:
    """Get deal pipeline with stages."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/crm/v3/pipelines/deals/{pipeline_id}",
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, dict) else {}


async def search_contacts(
    token: str,
    query: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search contacts by query string."""
    payload = {
        "query": query,
        "limit": min(limit, 100),
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_BASE}/crm/v3/objects/contacts/search",
            json=payload,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        return results if isinstance(results, list) else []


async def get_owner(token: str) -> dict[str, Any]:
    """Get account info (verifies token)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/crm/v3/owners",
            params={"limit": 1},
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, dict) else {}
