"""Tests for DigitalOcean integration endpoints."""
from unittest.mock import AsyncMock

from app.services import do_service


async def test_do_connect_returns_201(client, monkeypatch):
    monkeypatch.setattr(do_service, "connect_digitalocean", AsyncMock(return_value={
        "connected": True,
        "team_name": "TestTeam",
    }))
    monkeypatch.setattr(do_service, "get_digitalocean_status", AsyncMock(return_value={
        "connected": True,
        "team_name": "TestTeam",
    }))
    resp = await client.post(
        "/api/v1/integrations/digitalocean/connect",
        json={"api_token": "dop_test_fake_token"},
    )
    assert resp.status_code == 201


async def test_do_status_not_connected(client, monkeypatch):
    monkeypatch.setattr(do_service, "get_digitalocean_status", AsyncMock(return_value={
        "connected": False,
    }))
    resp = await client.get("/api/v1/integrations/digitalocean/status")
    assert resp.status_code == 200


async def test_do_sync_returns_result(client, monkeypatch):
    monkeypatch.setattr(do_service, "sync_digitalocean", AsyncMock(return_value={
        "droplets": 2,
        "members": 3,
    }))
    resp = await client.post("/api/v1/integrations/digitalocean/sync")
    assert resp.status_code == 200


async def test_do_sync_malformed_result_returns_502(client, monkeypatch):
    monkeypatch.setattr(do_service, "sync_digitalocean", AsyncMock(return_value={
        "droplets": "2",
        "members": 3,
    }))
    resp = await client.post("/api/v1/integrations/digitalocean/sync")
    assert resp.status_code == 502


async def test_do_sync_timeout_returns_502(client, monkeypatch):
    monkeypatch.setattr(do_service, "sync_digitalocean", AsyncMock(side_effect=TimeoutError("do timeout")))
    resp = await client.post("/api/v1/integrations/digitalocean/sync")
    assert resp.status_code == 502
