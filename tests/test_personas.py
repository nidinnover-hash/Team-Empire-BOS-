"""Tests for the persona dashboard endpoint."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clone_control import EmployeeCloneProfile
from app.models.clone_memory import CloneMemoryEntry
from app.models.clone_performance import ClonePerformanceWeekly
from app.models.employee import Employee
from app.services import persona as persona_service


async def _seed(db: AsyncSession):
    emp = Employee(
        organization_id=1,
        name="Test Clone",
        email="clone@test.com",
        role="Engineer",
        employment_status="active",
    )
    db.add(emp)
    await db.flush()

    profile = EmployeeCloneProfile(
        organization_id=1,
        employee_id=emp.id,
    )
    db.add(profile)
    await db.flush()

    perf = ClonePerformanceWeekly(
        organization_id=1,
        employee_id=emp.id,
        week_start_date=date.today(),
        productivity_score=0.8,
        quality_score=0.75,
        collaboration_score=0.9,
        learning_score=0.7,
        overall_score=0.79,
        readiness_level="ready",
    )
    db.add(perf)

    mem = CloneMemoryEntry(
        organization_id=1,
        employee_id=emp.id,
        situation="Client asked about pricing",
        action_taken="Provided tiered pricing overview",
        outcome="success",
        confidence=0.85,
    )
    db.add(mem)
    await db.commit()
    return emp.id


@pytest.mark.asyncio
async def test_persona_dashboard_service_no_data(db: AsyncSession):
    result = await persona_service.get_persona_dashboard(db, organization_id=999)
    assert result.kpis.total_clones == 0
    assert result.rows == []


@pytest.mark.asyncio
async def test_persona_dashboard_service_with_data(db: AsyncSession):
    emp_id = await _seed(db)
    result = await persona_service.get_persona_dashboard(db, organization_id=1)

    assert result.kpis.total_clones == 1
    assert result.kpis.avg_ai_level == 0.79
    assert result.kpis.ready_count == 1
    assert len(result.rows) == 1

    row = result.rows[0]
    assert row.employee_id == emp_id
    assert row.employee_name == "Test Clone"
    assert row.readiness == "ready"
    assert row.confidence == 0.85
    assert row.memory_count == 1


@pytest.mark.asyncio
async def test_persona_dashboard_endpoint(client):
    resp = await client.get("/api/v1/personas/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "kpis" in data
    assert "rows" in data
    assert "total_clones" in data["kpis"]
    assert "avg_ai_level" in data["kpis"]
    assert "ready_count" in data["kpis"]


@pytest.mark.asyncio
async def test_persona_dashboard_endpoint_returns_valid_shape(client):
    # Shape is all we can check without seeding clone profiles via API
    resp = await client.get("/api/v1/personas/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["kpis"]["total_clones"], int)
    assert isinstance(data["kpis"]["avg_ai_level"], float)
    assert isinstance(data["kpis"]["ready_count"], int)
    assert isinstance(data["rows"], list)
