"""Tests for governance policies, violations, compliance, and automation level."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.employee import Employee
from app.models.employee_work_pattern import EmployeeWorkPattern
from app.models.event import Event
from app.schemas.governance import GovernancePolicyCreate
from app.services import governance as gov_service


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


@pytest.mark.asyncio
async def test_create_policy(client):
    resp = await client.post("/api/v1/governance/policies", json={
        "name": "Min Work Hours",
        "policy_type": "performance",
        "description": "Employees must work at least 6 hours/day",
        "rules_json": {"min_hours_per_day": 6},
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Min Work Hours"
    assert data["policy_type"] == "performance"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_policies(client):
    await client.post("/api/v1/governance/policies", json={
        "name": "Policy A", "policy_type": "general", "rules_json": {},
    })
    resp = await client.get("/api/v1/governance/policies")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_update_policy(client):
    create = await client.post("/api/v1/governance/policies", json={
        "name": "Draft", "policy_type": "security", "rules_json": {},
    })
    pid = create.json()["id"]
    resp = await client.patch(f"/api/v1/governance/policies/{pid}", json={"name": "Final Policy"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Final Policy"


@pytest.mark.asyncio
async def test_evaluate_compliance(db: AsyncSession):
    """Policy violation should be detected for employee below threshold."""
    # Create policy
    await gov_service.create_policy(
        db, org_id=1,
        data=GovernancePolicyCreate(
            name="Min Hours", policy_type="performance",
            rules_json={"min_hours_per_day": 7},
        ),
    )

    # Create employee with low hours
    emp = Employee(
        organization_id=1, name="Lazy Worker", email="lazy@test.com",
        job_title="Staff", employment_status="active",
    )
    db.add(emp)
    await db.flush()

    today = date.today()
    for i in range(3):
        d = today - timedelta(days=i)
        db.add(EmployeeWorkPattern(
            organization_id=1, employee_id=emp.id, work_date=d,
            hours_logged=3.0, active_minutes=150, focus_minutes=60,
            meetings_minutes=30, tasks_completed=1, source="test",
        ))
    await db.commit()

    violations = await gov_service.evaluate_compliance(db, org_id=1)
    assert len(violations) >= 1
    assert any(v["employee_name"] == "Lazy Worker" for v in violations)


@pytest.mark.asyncio
async def test_resolve_violation(client):
    # Create policy and evaluate
    await client.post("/api/v1/governance/policies", json={
        "name": "Test Policy", "policy_type": "general",
        "rules_json": {"min_hours_per_day": 99},  # impossible threshold
    })

    # Create an employee
    await client.post("/api/v1/ops/employees", json={
        "name": "Test Emp", "email": "testemp@test.com",
    })

    # Run compliance check
    await client.post("/api/v1/governance/evaluate")

    # Get violations
    resp = await client.get("/api/v1/governance/violations")
    violations = resp.json()

    if violations:
        vid = violations[0]["id"]
        resolve_resp = await client.post(f"/api/v1/governance/violations/{vid}/resolve?status=resolved")
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_governance_dashboard(client):
    resp = await client.get("/api/v1/governance/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_policies" in data
    assert "open_violations" in data
    assert "compliance_rate" in data


@pytest.mark.asyncio
async def test_automation_level(client):
    resp = await client.get("/api/v1/governance/automation-level")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_level" in data
    assert data["current_level"] >= 0.05
    assert data["current_level"] <= 0.95
    assert "human_control" in data
    assert "reasoning" in data


@pytest.mark.asyncio
async def test_automation_level_starts_low(db: AsyncSession):
    """With no data, automation level should be near 5%."""
    level = await gov_service.calculate_automation_level(db, org_id=1)
    assert level.current_level <= 0.15  # should be low with no data
    assert level.human_control >= 0.85


@pytest.mark.asyncio
async def test_policy_drift_endpoint(client):
    resp = await client.get("/api/v1/governance/policy-drift?window_days=14")
    assert resp.status_code == 200
    body = resp.json()
    assert "generated_at" in body
    assert "window_days" in body
    assert "status" in body
    assert "signals" in body


@pytest.mark.asyncio
async def test_policy_drift_trend_endpoint(client):
    first = await client.get("/api/v1/governance/policy-drift?window_days=14")
    assert first.status_code == 200
    second = await client.get("/api/v1/governance/policy-drift?window_days=14")
    assert second.status_code == 200

    resp = await client.get("/api/v1/governance/policy-drift/trend?limit=14")
    assert resp.status_code == 200
    body = resp.json()
    assert "points" in body
    assert isinstance(body["points"], list)
    if body["points"]:
        point = body["points"][-1]
        assert "timestamp" in point
        assert "max_drift_percent" in point
        assert "signal_count" in point


@pytest.mark.asyncio
async def test_policy_drift_trend_limit_and_ordering(client):
    session, agen = await _get_session()
    try:
        base = datetime.now(UTC) - timedelta(minutes=20)
        for idx in range(5):
            session.add(
                Event(
                    organization_id=1,
                    event_type="governance_policy_drift_detected",
                    actor_user_id=1,
                    entity_type="governance",
                    entity_id=None,
                    payload_json={"max_drift_percent": float(idx), "signals": idx},
                    created_at=base + timedelta(minutes=idx),
                )
            )
        await session.commit()

        resp = await client.get("/api/v1/governance/policy-drift/trend?limit=3")
        assert resp.status_code == 200
        points = resp.json()["points"]
        assert len(points) == 3
        assert [float(p["max_drift_percent"]) for p in points] == [2.0, 3.0, 4.0]
        parsed = [datetime.fromisoformat(str(p["timestamp"]).replace("Z", "+00:00")) for p in points]
        assert parsed[0] <= parsed[1] <= parsed[2]
    finally:
        await agen.aclose()
