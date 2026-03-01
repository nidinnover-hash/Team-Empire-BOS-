"""Tests for /api/v1/ops endpoints — employees, decision-log, policies."""

from datetime import UTC, datetime, timedelta

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.event import Event


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


async def test_list_employees_empty(client):
    resp = await client.get("/api/v1/ops/employees")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_employee_returns_201(client):
    resp = await client.post(
        "/api/v1/ops/employees",
        json={"name": "Alice", "role": "Engineer", "email": "alice@test.com"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Alice"
    assert body["role"] == "Engineer"


async def test_get_employee_after_create(client):
    create = await client.post(
        "/api/v1/ops/employees",
        json={"name": "Bob", "role": "Designer", "email": "bob@test.com"},
    )
    eid = create.json()["id"]
    resp = await client.get(f"/api/v1/ops/employees/{eid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Bob"


async def test_decision_log_empty(client):
    resp = await client.get("/api/v1/ops/decision-log")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_decision_log_entry(client):
    resp = await client.post(
        "/api/v1/ops/decision-log",
        json={
            "decision_type": "approve",
            "context": "Growing team",
            "objective": "Hire new dev",
            "reason": "Team capacity",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["objective"] == "Hire new dev"


async def test_list_policies_empty(client):
    resp = await client.get("/api/v1/ops/policies")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_daily_runs_list_empty(client):
    resp = await client.get("/api/v1/ops/daily-runs")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_incident_command_mode_endpoint(client):
    resp = await client.get("/api/v1/ops/incident/command-mode")
    assert resp.status_code == 200
    body = resp.json()
    assert "incident_level" in body
    assert "score" in body
    assert "triggers" in body
    assert "top_actions" in body


async def test_incident_command_mode_trend_endpoint(client):
    first = await client.get("/api/v1/ops/incident/command-mode")
    assert first.status_code == 200
    second = await client.get("/api/v1/ops/incident/command-mode")
    assert second.status_code == 200

    resp = await client.get("/api/v1/ops/incident/command-mode/trend?limit=14")
    assert resp.status_code == 200
    body = resp.json()
    assert "points" in body
    assert isinstance(body["points"], list)
    if body["points"]:
        point = body["points"][-1]
        assert "timestamp" in point
        assert "score" in point
        assert "incident_level" in point


async def test_incident_command_mode_trend_limit_and_ordering(client):
    session, agen = await _get_session()
    try:
        base = datetime.now(UTC) - timedelta(minutes=15)
        levels = ["green", "amber", "red", "amber", "green"]
        for idx in range(5):
            session.add(
                Event(
                    organization_id=1,
                    event_type="incident_command_mode_viewed",
                    actor_user_id=1,
                    entity_type="ops_incident",
                    entity_id=None,
                    payload_json={"score": idx, "incident_level": levels[idx]},
                    created_at=base + timedelta(minutes=idx),
                )
            )
        await session.commit()

        resp = await client.get("/api/v1/ops/incident/command-mode/trend?limit=3")
        assert resp.status_code == 200
        points = resp.json()["points"]
        assert len(points) == 3
        assert [int(p["score"]) for p in points] == [2, 3, 4]
        parsed = [datetime.fromisoformat(str(p["timestamp"]).replace("Z", "+00:00")) for p in points]
        assert parsed[0] <= parsed[1] <= parsed[2]
    finally:
        await agen.aclose()
