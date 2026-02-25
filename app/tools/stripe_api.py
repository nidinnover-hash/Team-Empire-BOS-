"""Stripe API — payment and transaction data.

Pure async httpx client, no DB.
Uses Stripe REST API with secret key authentication.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.stripe.com/v1"
_TIMEOUT = 20.0


def _headers(secret_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret_key}"}


async def list_charges(
    secret_key: str,
    *,
    limit: int = 25,
    created_gte: int | None = None,
) -> list[dict[str, Any]]:
    """List recent charges (payments)."""
    params: dict[str, Any] = {"limit": min(limit, 100)}
    if created_gte:
        params["created[gte]"] = created_gte
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/charges", params=params, headers=_headers(secret_key))
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", [])
        return data if isinstance(data, list) else []


async def list_refunds(
    secret_key: str,
    *,
    limit: int = 25,
    created_gte: int | None = None,
) -> list[dict[str, Any]]:
    """List recent refunds."""
    params: dict[str, Any] = {"limit": min(limit, 100)}
    if created_gte:
        params["created[gte]"] = created_gte
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/refunds", params=params, headers=_headers(secret_key))
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", [])
        return data if isinstance(data, list) else []


async def list_disputes(
    secret_key: str,
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """List payment disputes (chargebacks)."""
    params = {"limit": min(limit, 100)}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/disputes", params=params, headers=_headers(secret_key))
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", [])
        return data if isinstance(data, list) else []


async def get_balance(secret_key: str) -> dict[str, Any]:
    """Get current Stripe balance."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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
    """List customers, optionally filtered by email."""
    params: dict[str, Any] = {"limit": min(limit, 100)}
    if email:
        params["email"] = email
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/customers", params=params, headers=_headers(secret_key))
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", [])
        return data if isinstance(data, list) else []


async def verify_key(secret_key: str) -> dict[str, Any]:
    """Verify the API key by fetching the balance."""
    return await get_balance(secret_key)
