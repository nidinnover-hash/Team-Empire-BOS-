"""Tests for global webhook delivery history endpoint."""

import pytest


@pytest.mark.asyncio
async def test_global_deliveries_empty(client):
    r = await client.get("/api/v1/webhooks/deliveries/all")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_global_deliveries_with_filters(client):
    r = await client.get("/api/v1/webhooks/deliveries/all?event=task.created&status=pending")
    assert r.status_code == 200
    assert "items" in r.json()
