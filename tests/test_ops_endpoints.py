"""Tests for /api/v1/ops endpoints — employees, decision-log, policies."""


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
