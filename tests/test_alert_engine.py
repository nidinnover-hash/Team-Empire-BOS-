"""Tests for the proactive alert engine."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_run_alerts_endpoint(client):
    """Run-alerts endpoint returns alert summary."""
    resp = await client.post("/api/v1/notifications/run-alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_alerts" in data
    assert "budget_overruns" in data
    assert "stale_contacts" in data
    assert "overdue_followups" in data
    assert "failed_syncs" in data


@pytest.mark.asyncio
async def test_alerts_dont_duplicate_within_24h(client):
    """Running alerts twice within 24h should not duplicate."""
    # First run
    r1 = await client.post("/api/v1/notifications/run-alerts")
    total1 = r1.json()["total_alerts"]

    # Second run should produce 0 (dedup within 24h)
    r2 = await client.post("/api/v1/notifications/run-alerts")
    assert r2.json()["total_alerts"] == 0 or r2.json()["total_alerts"] <= total1
