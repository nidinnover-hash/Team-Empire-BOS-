"""LinkedIn Marketing API — post publishing and profile info.

Pure async httpx client, no DB.
Uses LinkedIn Marketing API v2 (OAuth 2.0 access token).
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.linkedin.com/v2"
_TIMEOUT = 20.0


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


async def get_profile(token: str) -> dict[str, Any]:
    """Fetch the authenticated user's LinkedIn profile (name, URN)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/userinfo", headers=_headers(token))
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
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
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
    """Fetch engagement stats for a specific post."""
    params = {"q": "entity", "entity": post_urn}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            "https://api.linkedin.com/rest/socialMetadata",
            params=params,
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
