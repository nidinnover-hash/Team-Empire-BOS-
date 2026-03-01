"""Tests for the enriched Dashboard KPI endpoint."""

import pytest


@pytest.mark.asyncio
async def test_dashboard_kpis_returns_all_fields(client):
    r = await client.get("/api/v1/dashboard/kpis")
    assert r.status_code == 200
    data = r.json()
    assert "tasks_pending" in data
    assert "pending_approvals" in data
    assert "connected_integrations" in data
    assert "events_today" in data
    assert "active_triggers" in data
    assert "active_workflows" in data
    assert "webhook_deliveries_24h" in data
    assert "generated_at" in data


@pytest.mark.asyncio
async def test_dashboard_kpis_counts_are_integers(client):
    r = await client.get("/api/v1/dashboard/kpis")
    data = r.json()
    for key in ("tasks_pending", "pending_approvals", "connected_integrations",
                "events_today", "active_triggers", "active_workflows", "webhook_deliveries_24h"):
        assert isinstance(data[key], int), f"{key} should be int, got {type(data[key])}"


@pytest.mark.asyncio
async def test_dashboard_kpis_reflects_new_trigger(client):
    # Create a trigger
    await client.post("/api/v1/automations/triggers", json={
        "name": "KPI trigger", "source_event": "e1", "action_type": "a1",
    })
    r = await client.get("/api/v1/dashboard/kpis")
    assert r.json()["active_triggers"] >= 1
