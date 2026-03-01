"""Google Analytics 4 Data API — website metrics.

Pure async httpx client, no DB.
Uses GA4 Data API v1beta with OAuth access token.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://analyticsdata.googleapis.com/v1beta"
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


async def run_report(
    token: str,
    property_id: str,
    *,
    start_date: str = "30daysAgo",
    end_date: str = "today",
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Run a GA4 report and return the raw response."""
    if not metrics:
        metrics = ["sessions", "activeUsers", "screenPageViews", "bounceRate"]
    payload: dict[str, Any] = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
    }
    if dimensions:
        payload["dimensions"] = [{"name": d} for d in dimensions]
    c = _get_client()
    resp = await c.post(
        f"{_BASE}/properties/{property_id}:runReport",
        json=payload,
        headers=_headers(token),
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def get_realtime(
    token: str,
    property_id: str,
) -> dict[str, Any]:
    """Get real-time active users."""
    payload = {
        "metrics": [{"name": "activeUsers"}],
    }
    c = _get_client()
    resp = await c.post(
        f"{_BASE}/properties/{property_id}:runRealtimeReport",
        json=payload,
        headers=_headers(token),
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def get_traffic_sources(
    token: str,
    property_id: str,
    *,
    start_date: str = "30daysAgo",
    end_date: str = "today",
) -> dict[str, Any]:
    """Get traffic by source/medium."""
    return await run_report(
        token,
        property_id,
        start_date=start_date,
        end_date=end_date,
        metrics=["sessions", "activeUsers", "conversions"],
        dimensions=["sessionSource", "sessionMedium"],
        limit=20,
    )


async def get_top_pages(
    token: str,
    property_id: str,
    *,
    start_date: str = "30daysAgo",
    end_date: str = "today",
) -> dict[str, Any]:
    """Get top pages by pageviews."""
    return await run_report(
        token,
        property_id,
        start_date=start_date,
        end_date=end_date,
        metrics=["screenPageViews", "activeUsers", "averageSessionDuration"],
        dimensions=["pagePath"],
        limit=20,
    )
