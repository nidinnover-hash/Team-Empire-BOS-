"""Tests for automation system polish — templates, scheduler, job queue stats, definitions."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

# ── Workflow Templates ────────────────────────────────────────────────────


def test_get_templates():
    from app.services.workflow_templates import get_templates
    templates = get_templates()
    assert len(templates) >= 5
    for t in templates:
        assert "id" in t
        assert "name" in t
        assert "category" in t
        assert "step_count" in t
        assert t["step_count"] > 0


def test_get_template_by_id():
    from app.services.workflow_templates import get_template_by_id
    t = get_template_by_id("lead-follow-up")
    assert t is not None
    assert t["name"] == "Lead Follow-Up Sequence"
    assert len(t["steps"]) >= 3
    for step in t["steps"]:
        assert "key" in step
        assert "action_type" in step


def test_get_template_by_id_not_found():
    from app.services.workflow_templates import get_template_by_id
    assert get_template_by_id("nonexistent") is None


def test_template_categories():
    from app.services.workflow_templates import get_templates
    templates = get_templates()
    categories = {t["category"] for t in templates}
    assert "sales" in categories
    assert "operations" in categories


# ── Automation Scheduler — Cron Parsing ───────────────────────────────────


def test_cron_matches_every_minute():
    from app.services.automation_scheduler import _cron_matches_now
    now = datetime(2026, 3, 9, 10, 30, 0, tzinfo=UTC)
    assert _cron_matches_now("* * * * *", now) is True


def test_cron_matches_specific_time():
    from app.services.automation_scheduler import _cron_matches_now
    # Monday 2026-03-09 is actually a Monday (weekday=0, cron dow=1)
    now = datetime(2026, 3, 9, 8, 0, 0, tzinfo=UTC)
    assert _cron_matches_now("0 8 * * 1", now) is True


def test_cron_no_match_wrong_minute():
    from app.services.automation_scheduler import _cron_matches_now
    now = datetime(2026, 3, 9, 8, 15, 0, tzinfo=UTC)
    assert _cron_matches_now("0 8 * * *", now) is False


def test_cron_range():
    from app.services.automation_scheduler import _cron_matches_now
    # Mon-Fri range (cron 1-5)
    # 2026-03-09 is Monday (cron dow=1)
    now = datetime(2026, 3, 9, 8, 0, 0, tzinfo=UTC)
    assert _cron_matches_now("0 8 * * 1-5", now) is True


def test_cron_step():
    from app.services.automation_scheduler import _cron_matches_now
    now = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
    assert _cron_matches_now("*/15 * * * *", now) is True
    now2 = datetime(2026, 3, 9, 10, 7, 0, tzinfo=UTC)
    assert _cron_matches_now("*/15 * * * *", now2) is False


def test_cron_invalid():
    from app.services.automation_scheduler import _cron_matches_now
    now = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
    assert _cron_matches_now("bad cron", now) is False
    assert _cron_matches_now("", now) is False


# ── Automation Scheduler — Due Detection ──────────────────────────────────


def test_definition_due_interval():
    from app.services.automation_scheduler import _is_definition_due

    class FakeDef:
        trigger_spec_json = {"interval_minutes": 30}

    now = datetime.now(UTC)
    last_run = now - timedelta(minutes=35)
    assert _is_definition_due(FakeDef(), now, last_run) is True

    last_run_recent = now - timedelta(minutes=10)
    assert _is_definition_due(FakeDef(), now, last_run_recent) is False


def test_definition_due_interval_first_run():
    from app.services.automation_scheduler import _is_definition_due

    class FakeDef:
        trigger_spec_json = {"interval_minutes": 60}

    now = datetime.now(UTC)
    assert _is_definition_due(FakeDef(), now, None) is True


def test_definition_due_cron():
    from app.services.automation_scheduler import _is_definition_due

    class FakeDef:
        trigger_spec_json = {"cron": "* * * * *"}

    now = datetime.now(UTC)
    old_run = now - timedelta(minutes=2)
    assert _is_definition_due(FakeDef(), now, old_run) is True


def test_definition_not_due_empty_spec():
    from app.services.automation_scheduler import _is_definition_due

    class FakeDef:
        trigger_spec_json = {}

    now = datetime.now(UTC)
    assert _is_definition_due(FakeDef(), now, None) is False


# ── Templates API Endpoint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_templates_endpoint(client):
    resp = await client.get("/api/v1/automations/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    assert all("id" in t and "name" in t for t in data)


@pytest.mark.asyncio
async def test_create_from_template_endpoint(client):
    resp = await client.post("/api/v1/automations/templates/lead-follow-up/create")
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Lead Follow-Up Sequence"
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_create_from_template_not_found(client):
    resp = await client.post("/api/v1/automations/templates/nonexistent/create")
    assert resp.status_code == 404


# ── Job Queue Stats Endpoint ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_queue_stats_endpoint(client):
    resp = await client.get("/api/v1/automations/job-queue-stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "pending" in data
    assert "worker_id" in data
    assert isinstance(data["worker_running"], bool)


# ── Workflow Definition Publish + Run ─────────────────────────────────────


@pytest.mark.asyncio
async def test_definition_publish_flow(client):
    # Create from template
    create_resp = await client.post("/api/v1/automations/templates/daily-briefing/create")
    assert create_resp.status_code == 201
    def_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "draft"

    # Publish
    pub_resp = await client.post(f"/api/v1/automations/workflow-definitions/{def_id}/publish")
    assert pub_resp.status_code == 200
    assert pub_resp.json()["status"] == "published"
    assert pub_resp.json()["version"] >= 1


# ── Job Handlers Registration ─────────────────────────────────────────────


def test_new_job_handlers_registered():
    """Verify that the new job handlers are registered."""
    import app.jobs.job_handlers  # noqa: F401
    from app.services.job_queue import _handlers

    assert "run_scheduled_workflows" in _handlers
    assert "run_workflow" in _handlers


# ── Feature Flags Default On ──────────────────────────────────────────────


def test_workflow_feature_flags_on():
    from app.core.config import settings
    assert settings.FEATURE_WORKFLOW_V2 is True
    assert settings.FEATURE_WORKFLOW_RUNS is True
    assert settings.FEATURE_WORKFLOW_COPILOT is True
    assert settings.FEATURE_WORKFLOW_EXEC_INSIGHTS is True
    assert settings.FEATURE_WORKFLOW_OBSERVABILITY is True
