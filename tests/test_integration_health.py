"""Tests for Integration Health Dashboard."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import _make_auth_headers

# ── Service tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_summary_empty(db):
    from app.services.integration_health import get_integration_health_summary

    result = await get_integration_health_summary(db, organization_id=9999)
    assert result["total"] == 0
    assert result["health_score"] == 0.0


@pytest.mark.asyncio
async def test_health_summary_with_integrations(db):
    from app.models.integration import Integration
    from app.services.integration_health import get_integration_health_summary

    # Healthy integration (synced recently)
    db.add(Integration(
        organization_id=1, type="test_healthy",
        status="connected", last_sync_at=datetime.now(UTC),
        last_sync_status="ok", sync_error_count=0,
    ))
    # Degraded integration (synced 48h ago)
    db.add(Integration(
        organization_id=1, type="test_degraded",
        status="connected", last_sync_at=datetime.now(UTC) - timedelta(hours=48),
        last_sync_status="ok", sync_error_count=0,
    ))
    # Error integration
    db.add(Integration(
        organization_id=1, type="test_errored",
        status="connected", last_sync_at=datetime.now(UTC),
        last_sync_status="error", sync_error_count=5,
    ))
    # Disconnected
    db.add(Integration(
        organization_id=1, type="test_disconnected",
        status="disconnected", sync_error_count=0,
    ))
    await db.flush()

    result = await get_integration_health_summary(db, organization_id=1)
    assert result["total"] >= 4
    assert result["connected"] >= 3
    assert result["healthy"] >= 1
    assert result["degraded"] >= 1
    assert result["errored"] >= 1
    assert result["disconnected"] >= 1


@pytest.mark.asyncio
async def test_health_details(db):
    from app.services.integration_health import get_integration_details

    result = await get_integration_details(db, organization_id=1)
    assert isinstance(result, list)
    for item in result:
        assert "type" in item
        assert "health" in item
        assert item["health"] in ("healthy", "degraded", "error", "disconnected", "never_synced")


@pytest.mark.asyncio
async def test_full_integration_health(db):
    from app.services.integration_health import get_full_integration_health

    result = await get_full_integration_health(db, organization_id=1)
    assert "summary" in result
    assert "integrations" in result
    assert isinstance(result["integrations"], list)


# ── API endpoint test ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_dashboard_endpoint(client):
    headers = _make_auth_headers()
    r = await client.get("/api/v1/integrations/health-dashboard", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "integrations" in data
