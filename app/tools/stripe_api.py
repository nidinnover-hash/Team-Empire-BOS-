"""Stripe API — payment and transaction data.

Pure async httpx client, no DB.
Uses Stripe REST API with secret key authentication.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.stripe.com/v1"
_TIMEOUT = 20.0

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


def _headers(secret_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret_key}"}


async def _paginated_list(
    secret_key: str,
    endpoint: str,
    *,
    limit: int,
    extra_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generic Stripe list pagination using starting_after cursor."""
    page_size = min(limit, 100)
    params: dict[str, Any] = {"limit": page_size}
    if extra_params:
        params.update(extra_params)
    client = _get_client()
    all_data: list[dict[str, Any]] = []
    while len(all_data) < limit:
        resp = await client.get(
            f"{_BASE}/{endpoint}", params=params, headers=_headers(secret_key),
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", [])
        if isinstance(data, list):
            all_data.extend(data)
        if not body.get("has_more") or not data:
            break
        params["starting_after"] = data[-1].get("id", "")
    return all_data[:limit]


async def list_charges(
    secret_key: str,
    *,
    limit: int = 25,
    created_gte: int | None = None,
) -> list[dict[str, Any]]:
    """List recent charges (payments) with auto-pagination."""
    extra: dict[str, Any] = {}
    if created_gte:
        extra["created[gte]"] = created_gte
    return await _paginated_list(secret_key, "charges", limit=limit, extra_params=extra)


async def list_refunds(
    secret_key: str,
    *,
    limit: int = 25,
    created_gte: int | None = None,
) -> list[dict[str, Any]]:
    """List recent refunds with auto-pagination."""
    extra: dict[str, Any] = {}
    if created_gte:
        extra["created[gte]"] = created_gte
    return await _paginated_list(secret_key, "refunds", limit=limit, extra_params=extra)


async def list_disputes(
    secret_key: str,
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """List payment disputes (chargebacks) with auto-pagination."""
    return await _paginated_list(secret_key, "disputes", limit=limit)


async def get_balance(secret_key: str) -> dict[str, Any]:
    """Get current Stripe balance."""
    client = _get_client()
    resp = await client.get(f"{_BASE}/balance", headers=_headers(secret_key))
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def list_customers(
    secret_key: str,
    *,
    limit: int = 25,
    email: str | None = None,
) -> list[dict[str, Any]]:
    """List customers with auto-pagination, optionally filtered by email."""
    extra: dict[str, Any] = {}
    if email:
        extra["email"] = email
    return await _paginated_list(secret_key, "customers", limit=limit, extra_params=extra)


async def verify_key(secret_key: str) -> dict[str, Any]:
    """Verify the API key by fetching the balance."""
    return await get_balance(secret_key)
