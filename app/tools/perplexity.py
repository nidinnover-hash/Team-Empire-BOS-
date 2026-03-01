"""Perplexity AI — real-time web search via Sonar API.

Pure async httpx client, no DB.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.perplexity.ai"
_TIMEOUT = 25.0

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


async def search(
    api_key: str,
    query: str,
    *,
    model: str = "sonar",
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Run a Perplexity Sonar search and return the raw response dict."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "max_tokens": max_tokens,
    }
    c = _get_client()
    resp = await c.post(f"{_BASE}/chat/completions", json=payload, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def search_news(
    api_key: str,
    topics: list[str],
    *,
    max_items: int = 10,
) -> list[dict[str, str]]:
    """Search for news across topics and return structured items."""
    query = (
        f"Give me the {max_items} most important recent news about: "
        + ", ".join(topics)
        + ". For each item return: title, one-sentence summary, and which topic it relates to."
    )
    result = await search(api_key, query, max_tokens=2048)
    content = ""
    choices = result.get("choices", [])
    if choices and isinstance(choices, list):
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
    citations = result.get("citations", [])
    return [{"content": content, "citations": citations}]


async def verify_key(api_key: str) -> bool:
    """Quick validation — send a tiny search to check the key works."""
    try:
        await search(api_key, "test", max_tokens=10)
        return True
    except httpx.HTTPStatusError:
        return False
