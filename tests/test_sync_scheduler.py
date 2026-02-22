"""
Tests for the background sync scheduler.

Verifies throttle logic, per-integration error isolation, and
that on-demand sync fires exactly once within the throttle window.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.services import sync_scheduler


# ── helpers ───────────────────────────────────────────────────────────────────

def _reset_state():
    sync_scheduler._last_synced.clear()


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
    recent = datetime.now(timezone.utc) - timedelta(minutes=_throttle_minutes() - 2)
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
    old = datetime.now(timezone.utc) - timedelta(minutes=_throttle_minutes() + 1)
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


# ── scheduler start/stop ──────────────────────────────────────────────────────

async def test_start_stop_scheduler():
    """start_scheduler creates a task; stop_scheduler cancels it."""
    sync_scheduler._scheduler_task = None

    task = sync_scheduler.start_scheduler(interval_minutes=9999)
    assert task is not None
    assert not task.done()

    sync_scheduler.stop_scheduler()
    # Give the event loop a tick to process the cancellation
    await asyncio.sleep(0)
    assert sync_scheduler._scheduler_task is None
