from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.domains.automation import service as automation_domain
from app.engines.execution.workflow_recovery import recover_workflow_runs_for_org
from app.services import sync_scheduler


@pytest.fixture(autouse=True)
def _workflow_reliability_flags():
    saved = (
        settings.FEATURE_WORKFLOW_RELIABILITY,
        settings.WORKFLOW_HEARTBEAT_TIMEOUT_SECONDS,
        settings.WORKFLOW_RETRY_BASE_SECONDS,
        settings.WORKFLOW_RETRY_MAX_SECONDS,
    )
    object.__setattr__(settings, "FEATURE_WORKFLOW_RELIABILITY", True)
    object.__setattr__(settings, "WORKFLOW_HEARTBEAT_TIMEOUT_SECONDS", 60)
    object.__setattr__(settings, "WORKFLOW_RETRY_BASE_SECONDS", 0)
    object.__setattr__(settings, "WORKFLOW_RETRY_MAX_SECONDS", 0)
    yield
    object.__setattr__(settings, "FEATURE_WORKFLOW_RELIABILITY", saved[0])
    object.__setattr__(settings, "WORKFLOW_HEARTBEAT_TIMEOUT_SECONDS", saved[1])
    object.__setattr__(settings, "WORKFLOW_RETRY_BASE_SECONDS", saved[2])
    object.__setattr__(settings, "WORKFLOW_RETRY_MAX_SECONDS", saved[3])


@pytest.mark.asyncio
async def test_workflow_recovery_resumes_retry_wait_runs(db):
    definition = await automation_domain.create_workflow_definition(
        db,
        organization_id=1,
        workspace_id=None,
        actor_user_id=1,
        name="Retryable workflow",
        description=None,
        trigger_mode="manual",
        trigger_spec_json={},
        steps_json=[{"name": "Skip", "action_type": "unknown_noop", "params": {}}],
        defaults_json={},
        risk_level="low",
    )
    await automation_domain.publish_workflow_definition(
        db,
        organization_id=1,
        workflow_definition_id=definition.id,
        actor_user_id=1,
    )
    run, _step_runs = await automation_domain.create_workflow_run(
        db,
        organization_id=1,
        workspace_id=None,
        actor_user_id=1,
        definition=definition,
        trigger_source="manual",
        trigger_signal_id=None,
        idempotency_key="recovery-retry-wait",
        input_json={},
        context_json={},
        plan_snapshot_json={},
    )
    run.status = "retry_wait"
    run.next_retry_at = datetime.now(UTC) - timedelta(seconds=5)
    await db.commit()

    result = await recover_workflow_runs_for_org(db, organization_id=1, actor_user_id=1)
    await db.refresh(run)

    assert result["recovered"] == 1
    assert run.status == "completed"
    assert run.result_json["step_0"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_workflow_recovery_marks_stale_running_runs_failed(db):
    definition = await automation_domain.create_workflow_definition(
        db,
        organization_id=1,
        workspace_id=None,
        actor_user_id=1,
        name="Stuck workflow",
        description=None,
        trigger_mode="manual",
        trigger_spec_json={},
        steps_json=[{"name": "Read", "action_type": "fetch_calendar_digest", "params": {}}],
        defaults_json={},
        risk_level="low",
    )
    run, _step_runs = await automation_domain.create_workflow_run(
        db,
        organization_id=1,
        workspace_id=None,
        actor_user_id=1,
        definition=definition,
        trigger_source="manual",
        trigger_signal_id=None,
        idempotency_key="recovery-stuck-run",
        input_json={},
        context_json={},
        plan_snapshot_json={},
    )
    run.status = "running"
    run.last_heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    await db.commit()

    result = await recover_workflow_runs_for_org(db, organization_id=1, actor_user_id=1)
    await db.refresh(run)

    assert result["failed"] == 1
    assert run.status == "failed"
    assert run.error_summary == "workflow_run_stuck_timeout"


@pytest.mark.asyncio
async def test_scheduler_workflow_recovery_job_runs_when_flag_enabled(monkeypatch):
    calls: list[int] = []

    async def _noop(*_args, **_kwargs):
        return None

    async def _fake_recovery(_db, *, organization_id: int, actor_user_id: int | None = None, limit: int = 100):
        calls.append(organization_id)
        return {"inspected": 0, "recovered": 0, "failed": 0}

    monkeypatch.setattr(sync_scheduler, "_check_token_health_job", _noop)
    monkeypatch.setattr(sync_scheduler, "_check_goal_deadlines", _noop)
    monkeypatch.setattr(sync_scheduler, "_check_stale_tasks", _noop)
    monkeypatch.setattr(sync_scheduler, "_check_follow_up_contacts", _noop)
    monkeypatch.setattr(sync_scheduler, "_maybe_emit_daily_briefing_notification", _noop)
    monkeypatch.setattr(sync_scheduler, "_check_morning_briefing", _noop)
    monkeypatch.setattr(sync_scheduler, "_maybe_generate_daily_ceo_summary", _noop)
    monkeypatch.setattr(sync_scheduler, "_maybe_generate_daily_pending_digest", _noop)
    monkeypatch.setattr(sync_scheduler, "_maybe_generate_daily_empire_flow_digest", _noop)
    monkeypatch.setattr(sync_scheduler, "_publish_due_social_posts", _noop)
    monkeypatch.setattr(sync_scheduler, "_cleanup_old_chat_messages", _noop)
    monkeypatch.setattr(sync_scheduler, "_cleanup_old_logs", _noop)
    monkeypatch.setattr(sync_scheduler, "_cleanup_old_job_runs_and_snapshots", _noop)
    monkeypatch.setattr(sync_scheduler, "_auto_reject_expired_approvals", _noop)
    monkeypatch.setattr(sync_scheduler, "_snapshot_org_trends_job", _noop)
    monkeypatch.setattr(sync_scheduler, "_cleanup_old_trend_events", _noop)
    monkeypatch.setattr(sync_scheduler, "_snapshot_layer_scores_job", _noop)
    monkeypatch.setattr(sync_scheduler, "_monitor_scheduler_slos", _noop)
    monkeypatch.setattr("app.engines.execution.workflow_recovery.recover_workflow_runs_for_org", _fake_recovery)

    await sync_scheduler._run_automation_jobs_for_org(object(), 7)

    assert calls == [7]
