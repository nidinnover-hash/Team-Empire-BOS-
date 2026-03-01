"""Integration tests for trend endpoints: ordering, limit behavior, empty responses."""

import pytest

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.services import trend_telemetry


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


@pytest.mark.asyncio
async def test_security_trend_empty(client):
    resp = await client.get("/api/v1/integrations/security-center/trend?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "points" in data
    assert data["points"] == []


@pytest.mark.asyncio
async def test_security_trend_ordering(client, monkeypatch):
    """Points should be returned in chronological order (oldest first)."""
    monkeypatch.setattr(trend_telemetry, "get_security_center", _fake_security_center)
    monkeypatch.setattr(trend_telemetry, "record_trend_event", _make_unthrottled_writer())

    for _ in range(3):
        await client.get("/api/v1/integrations/security-center")

    resp = await client.get("/api/v1/integrations/security-center/trend?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    points = data["points"]
    if len(points) >= 2:
        timestamps = [p["timestamp"] for p in points]
        assert timestamps == sorted(timestamps), "Points should be in chronological order"


@pytest.mark.asyncio
async def test_security_trend_limit(client, monkeypatch):
    """Limit parameter should cap the number of returned points."""
    monkeypatch.setattr(trend_telemetry, "get_security_center", _fake_security_center)
    monkeypatch.setattr(trend_telemetry, "record_trend_event", _make_unthrottled_writer())

    for _ in range(5):
        await client.get("/api/v1/integrations/security-center")

    resp = await client.get("/api/v1/integrations/security-center/trend?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()["points"]) <= 2


@pytest.mark.asyncio
async def test_security_trend_cursor_pagination(client, monkeypatch):
    monkeypatch.setattr(trend_telemetry, "get_security_center", _fake_security_center)
    monkeypatch.setattr(trend_telemetry, "record_trend_event", _make_unthrottled_writer())

    for _ in range(5):
        await client.get("/api/v1/integrations/security-center")

    page1 = await client.get("/api/v1/integrations/security-center/trend?limit=2")
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["points"]) == 2
    assert body1.get("next_cursor")

    page2 = await client.get(
        "/api/v1/integrations/security-center/trend",
        params={"limit": 2, "cursor": body1["next_cursor"]},
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["points"]) >= 1
    page1_oldest = body1["points"][0]["timestamp"]
    page2_newest = body2["points"][-1]["timestamp"]
    assert page2_newest <= page1_oldest


@pytest.mark.asyncio
async def test_security_trend_limit_validation(client):
    """Limit must be >= 2 and <= 60."""
    resp = await client.get("/api/v1/integrations/security-center/trend?limit=1")
    assert resp.status_code == 422

    resp = await client.get("/api/v1/integrations/security-center/trend?limit=100")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_policy_drift_trend_empty(client):
    resp = await client.get("/api/v1/governance/policy-drift/trend?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["points"] == []


@pytest.mark.asyncio
async def test_policy_drift_trend_limit_validation(client):
    resp = await client.get("/api/v1/governance/policy-drift/trend?limit=0")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_incident_trend_empty(client):
    resp = await client.get("/api/v1/ops/incident/command-mode/trend?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["points"] == []


@pytest.mark.asyncio
async def test_incident_trend_limit_validation(client):
    resp = await client.get("/api/v1/ops/incident/command-mode/trend?limit=1")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trend_metrics_endpoint(client):
    resp = await client.get("/api/v1/control/trend/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "write_attempted" in data
    assert "read_requests" in data
    assert "read_latency_ms_avg" in data


@pytest.mark.asyncio
async def test_scheduler_snapshot_respects_feature_flag(client, monkeypatch):
    session, agen = await _get_session()
    try:
        async def _disabled(_db, _org_id):
            return False

        monkeypatch.setattr(trend_telemetry, "trend_snapshots_enabled", _disabled)
        result = await trend_telemetry.snapshot_org_trends(session, 1)
        assert result == {"written": 0, "skipped": 3}
    finally:
        await agen.aclose()


async def _fake_security_center(db, org_id):
    return {
        "risk_level": "low",
        "summary": {"rotation_overdue": 0, "rotation_due_soon": 1, "manual_required": 0},
        "tokens": [],
    }


def _make_unthrottled_writer():
    """Create a record_trend_event replacement that skips throttle."""
    from app.logs.audit import record_action

    async def _writer(
        db,
        *,
        org_id,
        event_type,
        payload_json,
        actor_user_id,
        entity_type,
        throttle_minutes=15,
    ):
        await record_action(
            db=db,
            event_type=event_type,
            actor_user_id=actor_user_id,
            organization_id=org_id,
            entity_type=entity_type,
            entity_id=None,
            payload_json=payload_json,
        )
        return True

    return _writer
