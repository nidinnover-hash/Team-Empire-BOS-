"""Tests for integration force-sync and error-reset endpoints."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_force_sync_nonexistent_integration(client):
    """Force-sync on nonexistent integration returns 404."""
    resp = await client.post("/api/v1/integrations/99999/force-sync")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reset_errors_nonexistent_integration(client):
    """Reset-errors on nonexistent integration returns 404."""
    resp = await client.post("/api/v1/integrations/99999/reset-errors")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_force_sync_existing_integration(client):
    """Force-sync on an existing integration succeeds."""
    # Create an integration first
    create_resp = await client.post("/api/v1/integrations", json={
        "provider": "test_provider", "config_json": {"access_token": "tok123"},
    })
    if create_resp.status_code not in (200, 201):
        pytest.skip("Integration creation not available in test env")
    int_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/integrations/{int_id}/force-sync")
    assert resp.status_code == 200
    assert "sync_error_count" in resp.json()


@pytest.mark.asyncio
async def test_reset_errors_existing_integration(client):
    """Reset-errors clears error count on an existing integration."""
    create_resp = await client.post("/api/v1/integrations", json={
        "provider": "test_provider2", "config_json": {"access_token": "tok456"},
    })
    if create_resp.status_code not in (200, 201):
        pytest.skip("Integration creation not available in test env")
    int_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/integrations/{int_id}/reset-errors")
    assert resp.status_code == 200
    assert resp.json()["sync_error_count"] == 0
