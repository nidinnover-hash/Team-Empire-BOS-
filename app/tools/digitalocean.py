from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

_TIMEOUT = 20.0


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def _get(path: str, token: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    base = settings.DIGITALOCEAN_BASE_URL.rstrip("/")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{base}{path}", headers=_headers(token), params=params)
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, dict) else {}


async def list_droplets(token: str) -> list[dict[str, Any]]:
    body = await _get("/droplets", token, params={"per_page": 200})
    droplets = body.get("droplets")
    if not isinstance(droplets, list):
        return []
    return [d for d in droplets if isinstance(d, dict)]


async def list_team_members(token: str) -> list[dict[str, Any]]:
    body = await _get("/account/members", token, params={"per_page": 200})
    members = body.get("members")
    if not isinstance(members, list):
        return []
    return [m for m in members if isinstance(m, dict)]


async def get_account(token: str) -> dict[str, Any]:
    body = await _get("/account", token)
    account = body.get("account")
    return account if isinstance(account, dict) else {}


async def get_balance(token: str) -> dict[str, Any]:
    return await _get("/customers/my/balance", token)

