"""Tests for /api/v1/observability endpoints."""
from unittest.mock import AsyncMock

from app.services import observability as obs_service


async def test_summary_returns_200(client, monkeypatch):
    monkeypatch.setattr(obs_service, "get_observability_summary", AsyncMock(return_value={
        "days": 7,
        "total_ai_calls": 0,
        "provider_stats": [],
        "fallback_rate": 0.0,
        "error_rate": 0.0,
        "total_approvals": 0,
        "rejection_rate": 0.0,
        "approval_breakdown": {},
        "runtime_stats": {},
    }))
    resp = await client.get("/api/v1/observability/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 7
    assert "total_ai_calls" in body


async def test_ai_calls_returns_list(client, monkeypatch):
    monkeypatch.setattr(obs_service, "get_recent_ai_calls", AsyncMock(return_value=[]))
    resp = await client.get("/api/v1/observability/ai-calls")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_decision_traces_returns_list(client, monkeypatch):
    monkeypatch.setattr(obs_service, "get_recent_decisions", AsyncMock(return_value=[]))
    resp = await client.get("/api/v1/observability/decision-traces")
    assert resp.status_code == 200
    assert resp.json() == []
