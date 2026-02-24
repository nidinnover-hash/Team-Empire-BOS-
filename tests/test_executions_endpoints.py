"""Tests for /api/v1/executions endpoint."""


async def test_list_executions_empty(client):
    resp = await client.get("/api/v1/executions")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_executions_with_status_filter(client):
    resp = await client.get("/api/v1/executions?status=running")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_executions_invalid_status_returns_422(client):
    resp = await client.get("/api/v1/executions?status=invalid_status")
    assert resp.status_code == 422
