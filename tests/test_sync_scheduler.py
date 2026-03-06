"""
Tests for the background sync scheduler.

Verifies throttle logic, per-integration error isolation, and
that on-demand sync fires exactly once within the throttle window.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services import sync_scheduler

# ── helpers ───────────────────────────────────────────────────────────────────

def _reset_state():
    sync_scheduler._last_synced.clear()
    sync_scheduler._last_ceo_summary_date_by_org.clear()
    sync_scheduler._last_pending_digest_date_by_org.clear()
    sync_scheduler._last_empire_flow_digest_date_by_org.clear()
    sync_scheduler._scheduler_retry_telemetry["operations_total"] = 0
    sync_scheduler._scheduler_retry_telemetry["operations_succeeded"] = 0
    sync_scheduler._scheduler_retry_telemetry["operations_failed"] = 0
    sync_scheduler._scheduler_retry_telemetry["retries_total"] = 0
    sync_scheduler._scheduler_retry_telemetry["backoff_seconds_total"] = 0.0
    sync_scheduler._scheduler_retry_telemetry["last_error_type"] = None
    sync_scheduler._scheduler_retry_telemetry["last_error_at"] = None
    sync_scheduler._scheduler_retry_telemetry["per_integration"] = {}


# ── throttle logic ────────────────────────────────────────────────────────────

async def test_trigger_fires_when_no_previous_sync(monkeypatch):
    """First call with no previous sync timestamp updates _last_synced."""
    _reset_state()

    async def _fake_run(db, org_id):
        pass

    monkeypatch.setattr(sync_scheduler, "_run_integrations", _fake_run)

    class _FakeDB:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(sync_scheduler, "AsyncSessionLocal", lambda: _FakeDB())

    assert 99 not in sync_scheduler._last_synced
    await sync_scheduler.trigger_sync_for_org(99)
    await asyncio.sleep(0.05)

    # timestamp should now be recorded
    assert 99 in sync_scheduler._last_synced


async def test_trigger_skips_within_throttle_window(monkeypatch):
    _reset_state()

    from app.services.sync_scheduler import _throttle_minutes
    recent = datetime.now(UTC) - timedelta(minutes=_throttle_minutes() - 2)
    sync_scheduler._last_synced[1] = recent

    calls: list[str] = []

    async def _fake_run(db, org_id):
        calls.append(str(org_id))

    monkeypatch.setattr(sync_scheduler, "_run_integrations", _fake_run)

    await sync_scheduler.trigger_sync_for_org(1)
    # Give any created tasks a chance to run
    await asyncio.sleep(0)

    # Should NOT have fired because we're within the throttle window
    assert calls == []


async def test_trigger_fires_after_throttle_window(monkeypatch):
    """Call after throttle window expires updates _last_synced."""
    _reset_state()

    from app.services.sync_scheduler import _throttle_minutes
    old = datetime.now(UTC) - timedelta(minutes=_throttle_minutes() + 1)
    sync_scheduler._last_synced[2] = old

    async def _fake_run(db, org_id):
        pass

    monkeypatch.setattr(sync_scheduler, "_run_integrations", _fake_run)

    class _FakeDB:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(sync_scheduler, "AsyncSessionLocal", lambda: _FakeDB())

    await sync_scheduler.trigger_sync_for_org(2)
    await asyncio.sleep(0.05)

    # timestamp should have been updated
    assert sync_scheduler._last_synced[2] > old


# ── error isolation ────────────────────────────────────────────────────────────

async def test_integration_error_does_not_stop_others(monkeypatch):
    """A failure in one integration must not prevent the rest from running."""
    _reset_state()

    results: list[str] = []

    # Simulate clickup failing, github and slack succeeding
    from app.services import clickup_service, github_service, slack_service

    async def _fail(db, org_id):
        raise RuntimeError("clickup exploded")

    async def _ok_github(db, org_id):
        results.append("github")
        return {}

    async def _ok_slack(db, org_id):
        results.append("slack")
        return {}

    monkeypatch.setattr(clickup_service, "sync_clickup_tasks", _fail)
    monkeypatch.setattr(github_service, "sync_github", _ok_github)
    monkeypatch.setattr(slack_service, "sync_slack_messages", _ok_slack)

    # Call _run_integrations directly with a dummy db session
    await sync_scheduler._run_integrations(object(), org_id=1)

    assert "github" in results
    assert "slack" in results


async def test_run_integrations_all_succeed(monkeypatch):
    _reset_state()

    results: list[str] = []

    from app.services import clickup_service, github_service, slack_service

    async def _ok(db, org_id):
        results.append("ok")
        return {}

    monkeypatch.setattr(clickup_service, "sync_clickup_tasks", _ok)
    monkeypatch.setattr(github_service, "sync_github", _ok)
    monkeypatch.setattr(slack_service, "sync_slack_messages", _ok)

    await sync_scheduler._run_integrations(object(), org_id=1)

    assert results == ["ok", "ok", "ok"]


async def test_integration_retry_path_recovers_and_continues(monkeypatch):
    _reset_state()
    from app.services import clickup_service, github_service, slack_service

    attempts = {"clickup": 0}
    results: list[str] = []

    async def _flaky_clickup(db, org_id):
        attempts["clickup"] += 1
        if attempts["clickup"] == 1:
            raise TimeoutError("temporary timeout")
        results.append("clickup")
        return {"synced": 1, "error": None}

    async def _ok_github(db, org_id):
        results.append("github")
        return {"prs_synced": 1, "issues_synced": 1, "error": None}

    async def _ok_slack(db, org_id):
        results.append("slack")
        return {"channels_synced": 1, "messages_read": 1, "error": None}

    monkeypatch.setattr(clickup_service, "sync_clickup_tasks", _flaky_clickup)
    monkeypatch.setattr(github_service, "sync_github", _ok_github)
    monkeypatch.setattr(slack_service, "sync_slack_messages", _ok_slack)

    await sync_scheduler._run_integrations(object(), org_id=1)

    assert attempts["clickup"] >= 2
    assert "clickup" in results
    assert "github" in results
    assert "slack" in results
    telemetry = sync_scheduler.get_scheduler_retry_telemetry()
    assert telemetry["retries_total"] >= 1
    # Verify per-integration that the three mocked integrations all succeeded
    per = telemetry["per_integration"]
    assert per.get("1:clickup", {}).get("operations_succeeded", 0) >= 1
    assert per.get("1:github", {}).get("operations_succeeded", 0) >= 1
    assert per.get("1:slack", {}).get("operations_succeeded", 0) >= 1


def test_scheduler_retry_telemetry_tracks_failures():
    _reset_state()
    sync_scheduler._record_retry_telemetry(
        org_id=1,
        integration="clickup",
        attempts=2,
        ok=False,
        error_type="TimeoutError",
    )
    telemetry = sync_scheduler.get_scheduler_retry_telemetry()
    assert telemetry["operations_total"] == 1
    assert telemetry["operations_failed"] == 1
    assert telemetry["retries_total"] == 1
    assert telemetry["backoff_seconds_total"] >= 1.0
    assert telemetry["last_error_type"] == "TimeoutError"


# ── scheduler start/stop ──────────────────────────────────────────────────────

async def test_start_stop_scheduler():
    """start_scheduler creates a task; stop_scheduler cancels it."""
    sync_scheduler._scheduler_task = None

    task = sync_scheduler.start_scheduler(interval_minutes=9999)
    assert task is not None
    assert not task.done()

    await sync_scheduler.stop_scheduler()
    # Give the event loop a tick to process the cancellation
    await asyncio.sleep(0)
    assert sync_scheduler._scheduler_task is None


def test_extract_top_risks_sorts_by_severity_and_limits():
    report: dict[str, object] = {
        "violations": [
            {"title": "A", "severity": "LOW", "platform": "github"},
            {"title": "B", "severity": "CRITICAL", "platform": "digitalocean"},
            {"title": "C", "severity": "HIGH", "platform": "clickup"},
            {"title": "D", "severity": "MED", "platform": "github"},
            {"title": "E", "severity": "CRITICAL", "platform": "clickup"},
            {"title": "F", "severity": "LOW", "platform": "slack"},
        ]
    }
    top = sync_scheduler._extract_top_risks(report, limit=5)
    assert len(top) == 5
    assert [str(x["title"]) for x in top[:2]] == ["B", "E"]


def test_format_ceo_risk_digest_includes_sections():
    text = sync_scheduler._format_ceo_risk_digest(
        org_id=1,
        generated_at="2026-02-24T09:00:00+00:00",
        top_risks=[{"severity": "HIGH", "title": "Risk A", "platform": "github"}],
        stale_integrations=[{"type": "github", "age_hours": 26.0, "last_sync_status": "ok"}],
    )
    assert "Top Risks:" in text
    assert "Integration SLA Alerts:" in text
    assert "Risk A" in text
    assert "github: 26.0h stale" in text


async def test_maybe_send_daily_ceo_slack_summary_respects_channel_config(monkeypatch):
    from app.core.config import settings

    previous_channel = settings.CEO_ALERTS_SLACK_CHANNEL_ID
    settings.CEO_ALERTS_SLACK_CHANNEL_ID = "C123CEO"
    calls: list[dict[str, str]] = []

    async def _fake_send_to_slack(_db, org_id: int, channel_id: str, text: str):
        calls.append({"org_id": str(org_id), "channel_id": channel_id, "text": text})
        return {"ok": True, "ts": "1.2"}

    monkeypatch.setattr("app.services.slack_service.send_to_slack", _fake_send_to_slack)
    try:
        await sync_scheduler._maybe_send_daily_ceo_slack_summary(
            db=SimpleNamespace(),
            org_id=7,
            top_risks=[],
            stale_integrations=[],
            generated_at="2026-02-24T09:00:00+00:00",
        )
    finally:
        settings.CEO_ALERTS_SLACK_CHANNEL_ID = previous_channel

    assert len(calls) == 1
    assert calls[0]["channel_id"] == "C123CEO"


def test_automation_jobs_include_daily_empire_flow_digest():
    import inspect

    source = inspect.getsource(sync_scheduler._run_automation_jobs_for_org)
    assert "daily_empire_flow_digest" in source
