"""HubSpot CRM API — contacts, deals, and pipeline data.

Pure async httpx client, no DB.
Uses HubSpot API v3 with Private App access token.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.hubapi.com"
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


async def list_contacts(
    token: str,
    *,
    limit: int = 50,
    properties: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List CRM contacts with auto-pagination up to *limit* items."""
    page_size = min(limit, 100)
    params: dict[str, Any] = {"limit": page_size}
    if properties:
        params["properties"] = ",".join(properties)
    client = _get_client()
    all_results: list[dict[str, Any]] = []
    after: str | None = None
    while len(all_results) < limit:
        if after:
            params["after"] = after
        resp = await client.get(
            f"{_BASE}/crm/v3/objects/contacts",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        if isinstance(results, list):
            all_results.extend(results)
        after = (body.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    return all_results[:limit]


async def search_contacts_updated_after(
    token: str,
    updated_after: str,
    *,
    limit: int = 100,
    properties: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search contacts modified after a given ISO timestamp (delta-sync)."""
    filters = [{"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": updated_after}]
    payload: dict[str, Any] = {
        "filterGroups": [{"filters": filters}],
        "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "ASCENDING"}],
        "limit": min(limit, 100),
    }
    if properties:
        payload["properties"] = properties
    client = _get_client()
    all_results: list[dict[str, Any]] = []
    after: str | int = 0
    while len(all_results) < limit:
        if after:
            payload["after"] = after
        resp = await client.post(
            f"{_BASE}/crm/v3/objects/contacts/search",
            json=payload,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        if isinstance(results, list):
            all_results.extend(results)
        paging = body.get("paging") or {}
        after = paging.get("next", {}).get("after", 0)
        if not after:
            break
    return all_results[:limit]


async def list_deals(
    token: str,
    *,
    limit: int = 50,
    properties: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List CRM deals with auto-pagination up to *limit* items."""
    page_size = min(limit, 100)
    params: dict[str, Any] = {"limit": page_size}
    if properties:
        params["properties"] = ",".join(properties)
    client = _get_client()
    all_results: list[dict[str, Any]] = []
    after: str | None = None
    while len(all_results) < limit:
        if after:
            params["after"] = after
        resp = await client.get(
            f"{_BASE}/crm/v3/objects/deals",
            params=params,
            headers=_headers(token),
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        if isinstance(results, list):
            all_results.extend(results)
        after = (body.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    return all_results[:limit]


async def get_deal_pipeline(
    token: str,
    pipeline_id: str = "default",
) -> dict[str, Any]:
    """Get deal pipeline with stages."""
    client = _get_client()
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
    client = _get_client()
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
    client = _get_client()
    resp = await client.get(
        f"{_BASE}/crm/v3/owners",
        params={"limit": 1},
        headers=_headers(token),
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}
