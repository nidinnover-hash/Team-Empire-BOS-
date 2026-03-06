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


# ── Trends endpoint ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_trends_returns_all_series(client):
    r = await client.get("/api/v1/dashboard/trends")
    assert r.status_code == 200
    data = r.json()
    for key in ("labels", "revenue", "income", "expenses", "tasks_completed", "events"):
        assert key in data, f"missing key: {key}"
        assert isinstance(data[key], list)


@pytest.mark.asyncio
async def test_dashboard_trends_default_14_days(client):
    r = await client.get("/api/v1/dashboard/trends")
    data = r.json()
    assert len(data["labels"]) == 14
    assert len(data["revenue"]) == 14
    assert len(data["tasks_completed"]) == 14
    assert len(data["events"]) == 14


@pytest.mark.asyncio
async def test_dashboard_trends_custom_days(client):
    r = await client.get("/api/v1/dashboard/trends?days=7")
    data = r.json()
    assert len(data["labels"]) == 7


@pytest.mark.asyncio
async def test_dashboard_trends_with_finance_data(client):
    """Trends include finance entries created via the API."""
    from datetime import date

    today = date.today().isoformat()
    await client.post("/api/v1/finance", json={
        "type": "income", "amount": 500, "category": "freelance",
        "entry_date": today, "description": "test income",
    })
    await client.post("/api/v1/finance", json={
        "type": "expense", "amount": 200, "category": "food",
        "entry_date": today, "description": "test expense",
    })
    r = await client.get("/api/v1/dashboard/trends?days=7")
    data = r.json()
    # Last element should reflect today's data
    assert data["income"][-1] >= 500
    assert data["expenses"][-1] >= 200
    assert data["revenue"][-1] >= 300  # 500 - 200
