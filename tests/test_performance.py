"""Tests for performance analytics and AI coaching endpoints."""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_plan import DailyTaskPlan
from app.models.department import Department
from app.models.email import Email
from app.models.employee import Employee
from app.models.employee_work_pattern import EmployeeWorkPattern
from app.models.memory import TeamMember
from app.services import performance as perf_service


async def _seed_perf_data(db: AsyncSession):
    """Seed department, employees, and work patterns for testing."""
    dept = Department(organization_id=1, name="TestDept", code="TD", is_active=True)
    db.add(dept)
    await db.flush()

    emp1 = Employee(
        organization_id=1, department_id=dept.id, name="Top Worker",
        email="top@test.com", role="Developer", employment_status="active",
    )
    emp2 = Employee(
        organization_id=1, department_id=dept.id, name="Low Worker",
        email="low@test.com", role="Intern", employment_status="active",
    )
    db.add_all([emp1, emp2])
    await db.flush()

    today = date.today()
    for i in range(5):
        d = today - timedelta(days=i)
        db.add(EmployeeWorkPattern(
            organization_id=1, employee_id=emp1.id, work_date=d,
            hours_logged=8.0, active_minutes=400, focus_minutes=300,
            meetings_minutes=60, tasks_completed=5, source="test",
        ))
        db.add(EmployeeWorkPattern(
            organization_id=1, employee_id=emp2.id, work_date=d,
            hours_logged=3.0, active_minutes=150, focus_minutes=30,
            meetings_minutes=100, tasks_completed=1, source="test",
        ))
    await db.commit()
    return dept.id, emp1.id, emp2.id


@pytest.mark.asyncio
async def test_employee_performance(db: AsyncSession):
    _, emp1_id, _ = await _seed_perf_data(db)
    result = await perf_service.get_employee_performance(db, emp1_id, org_id=1, days=30)
    assert result is not None
    assert result.employee_name == "Top Worker"
    assert result.avg_hours > 0
    assert result.composite_score > 0


@pytest.mark.asyncio
async def test_department_performance(db: AsyncSession):
    dept_id, _, _ = await _seed_perf_data(db)
    result = await perf_service.get_department_performance(db, dept_id, org_id=1, days=30)
    assert result is not None
    assert result.department_name == "TestDept"
    assert result.employee_count == 2


@pytest.mark.asyncio
async def test_org_performance(db: AsyncSession):
    await _seed_perf_data(db)
    result = await perf_service.get_org_performance(db, org_id=1, days=30)
    assert result.total_employees == 2
    assert result.avg_hours > 0


@pytest.mark.asyncio
async def test_top_performers(db: AsyncSession):
    await _seed_perf_data(db)
    top = await perf_service.get_top_performers(db, org_id=1, days=30, limit=5)
    assert len(top) == 2
    assert top[0].composite_score >= top[1].composite_score


@pytest.mark.asyncio
async def test_performance_alerts(db: AsyncSession):
    await _seed_perf_data(db)
    alerts = await perf_service.get_performance_alerts(db, org_id=1, days=30, threshold=0.5)
    # Low Worker should trigger an alert
    assert any(a.employee_name == "Low Worker" for a in alerts)


@pytest.mark.asyncio
async def test_performance_endpoint_employee(client):
    # No data — should return 404 for non-existent employee
    resp = await client.get("/api/v1/performance/employee/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_performance_endpoint_org(client):
    resp = await client.get("/api/v1/performance/org?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_employees" in data
    assert "avg_hours" in data


@pytest.mark.asyncio
async def test_performance_top_endpoint(client):
    resp = await client.get("/api/v1/performance/top?days=7&limit=5")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_performance_alerts_endpoint(client):
    resp = await client.get("/api/v1/performance/alerts?days=7&threshold=0.3")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_coaching_endpoint(client, monkeypatch):
    """AI coaching should return report even with no real AI provider."""
    # Create an employee first
    emp = await client.post("/api/v1/ops/employees", json={
        "name": "Coach Target", "email": "coach@test.com",
    })
    emp_id = emp.json()["id"]

    resp = await client.post(f"/api/v1/coaching/employee/{emp_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_org_improvement_plan_endpoint(client):
    resp = await client.post("/api/v1/coaching/org")
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_learning_insights_endpoint(client):
    resp = await client.get("/api/v1/coaching/insights?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_reports" in data
    assert "effectiveness" in data


@pytest.mark.asyncio
async def test_org_chart_and_skill_matrix_service(db: AsyncSession):
    lead = TeamMember(
        organization_id=1,
        name="Lead",
        role_title="Tech Lead",
        team="tech",
        reports_to_id=None,
        skills="python,architecture",
        ai_level=4,
        is_active=True,
    )
    db.add(lead)
    await db.flush()
    dev = TeamMember(
        organization_id=1,
        name="Dev",
        role_title="Developer",
        team="tech",
        reports_to_id=lead.id,
        skills="python,sql",
        ai_level=3,
        is_active=True,
    )
    db.add(dev)
    await db.commit()

    chart = await perf_service.get_org_chart(db, org_id=1)
    assert len(chart.nodes) >= 2
    assert len(chart.roots) >= 1

    matrix = await perf_service.get_skill_matrix(
        db,
        org_id=1,
        required_skills=["python", "sql", "communication"],
    )
    assert matrix.organization_id == 1
    assert "communication" in matrix.org_missing_skills


@pytest.mark.asyncio
async def test_workload_balancer_service(db: AsyncSession):
    member_a = TeamMember(
        organization_id=1,
        name="A",
        role_title="Engineer",
        team="tech",
        skills="python",
        ai_level=3,
        is_active=True,
    )
    member_b = TeamMember(
        organization_id=1,
        name="B",
        role_title="Engineer",
        team="tech",
        skills="python",
        ai_level=3,
        is_active=True,
    )
    db.add_all([member_a, member_b])
    await db.flush()

    today = date.today()
    db.add(
        DailyTaskPlan(
            organization_id=1,
            team_member_id=member_a.id,
            date=today,
            tasks_json=[
                {"title": "Task 1", "priority": "high"},
                {"title": "Task 2", "priority": "high"},
                {"title": "Task 3", "priority": "medium"},
                {"title": "Task 4", "priority": "medium"},
            ],
            status="draft",
        )
    )
    db.add(
        DailyTaskPlan(
            organization_id=1,
            team_member_id=member_b.id,
            date=today,
            tasks_json=[{"title": "Task 1", "priority": "low"}],
            status="draft",
        )
    )
    await db.commit()

    result = await perf_service.get_workload_balance(db, org_id=1, for_date=today)
    assert result.overloaded_count >= 1
    assert result.underloaded_count >= 1
    assert len(result.actions) >= 1


@pytest.mark.asyncio
async def test_department_okr_progress_service(db: AsyncSession):
    dept = Department(organization_id=1, name="OKR Dept", code="OKR", is_active=True)
    db.add(dept)
    await db.flush()
    emp = Employee(
        organization_id=1,
        department_id=dept.id,
        name="KR Worker",
        email="kr@test.com",
        role="Developer",
        employment_status="active",
    )
    db.add(emp)
    await db.flush()

    today = date.today()
    for i in range(5):
        d = today - timedelta(days=i)
        db.add(
            EmployeeWorkPattern(
                organization_id=1,
                employee_id=emp.id,
                work_date=d,
                hours_logged=7.5,
                active_minutes=360,
                focus_minutes=210,
                meetings_minutes=45,
                tasks_completed=6,
                source="test",
            )
        )
    db.add(
        Email(
            organization_id=1,
            gmail_id="okr-email-1",
            from_address="x@test.com",
            to_address="y@test.com",
            subject="Test",
            body_text="Test",
            is_read=False,
        )
    )
    await db.commit()

    snapshot = await perf_service.get_department_okr_progress(
        db,
        org_id=1,
        department_id=dept.id,
        from_date=today - timedelta(days=6),
        to_date=today,
    )
    assert snapshot is not None
    assert snapshot.department_name == "OKR Dept"
    assert len(snapshot.key_results) == 3


@pytest.mark.asyncio
async def test_new_performance_feature_endpoints(client):
    assert (await client.get("/api/v1/performance/org-chart")).status_code == 200
    assert (await client.get("/api/v1/performance/workload-balance")).status_code == 200
    assert (await client.get("/api/v1/performance/skills-matrix?required_skills=python")).status_code == 200
    assert (await client.get("/api/v1/performance/department/9999/okr-progress")).status_code == 404
