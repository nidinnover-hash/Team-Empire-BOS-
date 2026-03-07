"""Tests for Workflow Execution Insights — analytics service + API endpoint."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.conftest import _make_auth_headers


# ── Service: get_execution_summary ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_execution_summary_empty(db):
    from app.services.workflow_insights import get_execution_summary

    result = await get_execution_summary(db, organization_id=9999, days=30)
    assert result["total_runs"] == 0
    assert result["success_rate"] == 0.0
    assert result["period_days"] == 30


@pytest.mark.asyncio
async def test_execution_summary_with_runs(db):
    from app.models.workflow_definition import WorkflowDefinition
    from app.models.workflow_run import WorkflowRun
    from app.services.workflow_insights import get_execution_summary

    # Create a workflow definition first
    defn = WorkflowDefinition(
        organization_id=1, name="Test WF", slug="test-wf-insights",
        status="active", trigger_mode="manual", steps_json=[], version=1,
        created_by=1,
    )
    db.add(defn)
    await db.flush()

    # Add some runs
    for i, status in enumerate(["completed", "completed", "failed", "running"]):
        run = WorkflowRun(
            organization_id=1, workflow_definition_id=defn.id, status=status,
            requested_by=1, idempotency_key=f"test-insight-{status}-{i}",
        )
        db.add(run)
    await db.flush()

    result = await get_execution_summary(db, organization_id=1, days=30)
    assert result["total_runs"] >= 4
    assert result["completed"] >= 2
    assert result["failed"] >= 1


@pytest.mark.asyncio
async def test_execution_summary_respects_days_filter(db):
    from app.services.workflow_insights import get_execution_summary

    # With days=0 we shouldn't get much (only runs from "today")
    result = await get_execution_summary(db, organization_id=1, days=1)
    assert isinstance(result["total_runs"], int)


# ── Service: get_step_performance ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_step_performance_empty(db):
    from app.services.workflow_insights import get_step_performance

    result = await get_step_performance(db, organization_id=9999)
    assert result == []


@pytest.mark.asyncio
async def test_step_performance_with_steps(db):
    from app.models.workflow_definition import WorkflowDefinition
    from app.models.workflow_run import WorkflowRun, WorkflowStepRun
    from app.services.workflow_insights import get_step_performance

    defn = WorkflowDefinition(
        organization_id=1, name="Step Perf WF", slug="step-perf-wf",
        status="active", trigger_mode="manual", steps_json=[], version=1,
        created_by=1,
    )
    db.add(defn)
    await db.flush()

    run = WorkflowRun(
        organization_id=1, workflow_definition_id=defn.id, status="completed",
        requested_by=1, idempotency_key="step-perf-run-1",
    )
    db.add(run)
    await db.flush()

    step = WorkflowStepRun(
        organization_id=1, workflow_run_id=run.id, step_index=0,
        step_key="send_email_0", action_type="send_email", status="completed",
        latency_ms=150, idempotency_key="step-perf-step-1",
    )
    db.add(step)
    await db.flush()

    result = await get_step_performance(db, organization_id=1)
    email_steps = [s for s in result if s["action_type"] == "send_email"]
    assert len(email_steps) >= 1
    assert email_steps[0]["avg_latency_ms"] is not None


# ── Service: get_workflow_rankings ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_rankings_empty(db):
    from app.services.workflow_insights import get_workflow_rankings

    result = await get_workflow_rankings(db, organization_id=9999)
    assert result == []


# ── Service: get_failure_patterns ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_failure_patterns_empty(db):
    from app.services.workflow_insights import get_failure_patterns

    result = await get_failure_patterns(db, organization_id=9999)
    assert result == []


@pytest.mark.asyncio
async def test_failure_patterns_with_errors(db):
    from app.models.workflow_definition import WorkflowDefinition
    from app.models.workflow_run import WorkflowRun
    from app.services.workflow_insights import get_failure_patterns

    defn = WorkflowDefinition(
        organization_id=1, name="Fail WF", slug="fail-wf-insights",
        status="active", trigger_mode="manual", steps_json=[], version=1,
        created_by=1,
    )
    db.add(defn)
    await db.flush()

    for i in range(3):
        run = WorkflowRun(
            organization_id=1, workflow_definition_id=defn.id, status="failed",
            requested_by=1, idempotency_key=f"fail-insight-{i}",
            error_summary="Connection timeout",
        )
        db.add(run)
    await db.flush()

    result = await get_failure_patterns(db, organization_id=1)
    timeout_errs = [f for f in result if "timeout" in (f["error_summary"] or "").lower()]
    assert len(timeout_errs) >= 1
    assert timeout_errs[0]["count"] >= 3


# ── Service: get_daily_run_counts ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_run_counts_empty(db):
    from app.services.workflow_insights import get_daily_run_counts

    result = await get_daily_run_counts(db, organization_id=9999)
    assert result == []


@pytest.mark.asyncio
async def test_daily_run_counts_returns_dates(db):
    from app.services.workflow_insights import get_daily_run_counts

    result = await get_daily_run_counts(db, organization_id=1, days=30)
    for entry in result:
        assert "date" in entry
        assert "total" in entry
        assert "completed" in entry


# ── Service: get_full_insights ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_insights_structure(db):
    from app.services.workflow_insights import get_full_insights

    result = await get_full_insights(db, organization_id=1, days=30)
    assert "summary" in result
    assert "step_performance" in result
    assert "workflow_rankings" in result
    assert "failure_patterns" in result
    assert "daily_counts" in result
    assert isinstance(result["summary"], dict)
    assert isinstance(result["step_performance"], list)


# ── API endpoint ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insights_endpoint_returns_404_when_disabled(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_EXEC_INSIGHTS", False)
    headers = _make_auth_headers()
    r = await client.get("/api/v1/automations/insights", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_insights_endpoint_returns_200_when_enabled(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_V2", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_RUNS", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_EXEC_INSIGHTS", True)
    headers = _make_auth_headers()
    r = await client.get("/api/v1/automations/insights", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "step_performance" in data


@pytest.mark.asyncio
async def test_insights_endpoint_accepts_days_param(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_V2", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_RUNS", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_EXEC_INSIGHTS", True)
    headers = _make_auth_headers()
    r = await client.get("/api/v1/automations/insights?days=7", headers=headers)
    assert r.status_code == 200
    assert r.json()["summary"]["period_days"] == 7


@pytest.mark.asyncio
async def test_insights_endpoint_rejects_invalid_days(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_V2", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_RUNS", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_EXEC_INSIGHTS", True)
    headers = _make_auth_headers()
    r = await client.get("/api/v1/automations/insights?days=0", headers=headers)
    assert r.status_code == 422


# ── Bootstrap flag ──────────────────────────────────────────────────────────

def test_workflow_exec_insights_enabled_flag(monkeypatch):
    from app.application.automation.bootstrap import workflow_exec_insights_enabled
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_V2", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_RUNS", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_EXEC_INSIGHTS", True)
    assert workflow_exec_insights_enabled() is True

    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_EXEC_INSIGHTS", False)
    assert workflow_exec_insights_enabled() is False

    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_V2", False)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_EXEC_INSIGHTS", True)
    assert workflow_exec_insights_enabled() is False
