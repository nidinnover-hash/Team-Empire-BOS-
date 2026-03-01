"""Tests for self-learning feedback loops."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coaching_report import CoachingReport
from app.services import learning_feedback


@pytest.mark.asyncio
async def test_record_outcome(db: AsyncSession):
    # Create a coaching report first
    report = CoachingReport(
        organization_id=1,
        report_type="employee",
        title="Test Coaching",
        summary="Test summary",
        recommendations_json={"recommendations": [{"suggestion": "Work harder"}]},
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    result = await learning_feedback.record_outcome(
        db, org_id=1, coaching_report_id=report.id,
        was_applied=True, outcome_score=0.8, notes="Good results",
    )
    assert result["ok"] is True
    assert "outcome_id" in result


@pytest.mark.asyncio
async def test_record_outcome_not_found(db: AsyncSession):
    result = await learning_feedback.record_outcome(
        db, org_id=1, coaching_report_id=9999,
        was_applied=False, outcome_score=0.5,
    )
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_analyze_effectiveness(db: AsyncSession):
    result = await learning_feedback.analyze_effectiveness(db, org_id=1, days=30)
    assert "total_outcomes" in result
    assert "application_rate" in result


@pytest.mark.asyncio
async def test_get_learning_insights(db: AsyncSession):
    result = await learning_feedback.get_learning_insights(db, org_id=1, days=30)
    assert "effectiveness" in result
    assert "total_reports" in result
    assert "system_learning" in result


@pytest.mark.asyncio
async def test_learning_insights_endpoint(client):
    resp = await client.get("/api/v1/performance/learning-insights?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "system_learning" in data


@pytest.mark.asyncio
async def test_record_outcome_endpoint(client):
    # Create coaching report via AI coaching endpoint
    emp = await client.post("/api/v1/ops/employees", json={
        "name": "Feedback Target", "email": "feedback@test.com",
    })
    emp_id = emp.json()["id"]

    coaching = await client.post(f"/api/v1/performance/employee/{emp_id}/coaching")
    report_id = coaching.json()["report_id"]

    resp = await client.post(
        f"/api/v1/performance/outcomes?coaching_report_id={report_id}&was_applied=true&outcome_score=0.75"
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
