"""LinkedIn Marketing API — post publishing and profile info.

Pure async httpx client, no DB.
Uses LinkedIn Marketing API v2 (OAuth 2.0 access token).
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.linkedin.com/v2"
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
        "X-Restli-Protocol-Version": "2.0.0",
    }


async def get_profile(token: str) -> dict[str, Any]:
    """Fetch the authenticated user's LinkedIn profile (name, URN)."""
    c = _get_client()
    resp = await c.get(f"{_BASE}/userinfo", headers=_headers(token))
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def create_text_post(
    token: str,
    *,
    author_urn: str,
    text: str,
    visibility: str = "PUBLIC",
) -> dict[str, Any]:
    """Create a text-only LinkedIn post using the Posts API."""
    payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": visibility,
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
    }
    c = _get_client()
    resp = await c.post(
        "https://api.linkedin.com/rest/posts",
        json=payload,
        headers={
            **_headers(token),
            "LinkedIn-Version": "202401",
        },
    )
    resp.raise_for_status()
    # LinkedIn returns 201 with x-restli-id header
    post_id = resp.headers.get("x-restli-id", "")
    return {"id": post_id, "status": "published"}


async def get_post_stats(
    token: str,
    *,
    post_urn: str,
) -> dict[str, Any]:
    """Fetch engagement stats for a specific post via the socialActions endpoint."""
    c = _get_client()
    # LinkedIn REST API: socialActions returns likes/comments/shares for a post URN
    encoded_urn = post_urn.replace(":", "%3A").replace("(", "%28").replace(")", "%29")
    resp = await c.get(
        f"https://api.linkedin.com/rest/socialActions/{encoded_urn}",
        headers={
            **_headers(token),
            "LinkedIn-Version": "202401",
        },
    )
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def verify_token(token: str) -> dict[str, Any]:
    """Quick check — get profile to verify token is valid."""
    return await get_profile(token)
