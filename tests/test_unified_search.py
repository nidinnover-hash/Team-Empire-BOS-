"""Tests for unified search endpoint."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_search_returns_multiple_types(client):
    """Search returns results across different entity types."""
    await client.post("/api/v1/tasks", json={"title": "SearchTest task", "category": "business"})
    await client.post("/api/v1/contacts", json={"name": "SearchTest contact", "relationship": "business"})
    await client.post("/api/v1/deals", json={"title": "SearchTest deal", "value": 100.0})

    resp = await client.get("/api/v1/search?q=SearchTest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    types = {r["type"] for r in data["results"]}
    assert "task" in types
    assert "contact" in types
    assert "deal" in types


@pytest.mark.asyncio
async def test_search_filter_by_type(client):
    """Search can be filtered by entity type."""
    await client.post("/api/v1/tasks", json={"title": "FilterMe task", "category": "business"})
    await client.post("/api/v1/contacts", json={"name": "FilterMe contact", "relationship": "business"})

    resp = await client.get("/api/v1/search?q=FilterMe&types=task")
    data = resp.json()
    assert all(r["type"] == "task" for r in data["results"])


@pytest.mark.asyncio
async def test_search_empty_results(client):
    """Search with no matches returns empty."""
    resp = await client.get("/api/v1/search?q=xyznonexistent123")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_search_deals(client):
    """Search finds deals by title."""
    await client.post("/api/v1/deals", json={"title": "UniquePartnership2026"})

    resp = await client.get("/api/v1/search?q=UniquePartnership2026")
    data = resp.json()
    deal_results = [r for r in data["results"] if r["type"] == "deal"]
    assert len(deal_results) >= 1
