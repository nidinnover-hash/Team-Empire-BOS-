"""Tests for AI Coaching Pipeline — weekly job, service functions."""
from __future__ import annotations

import pytest

from tests.conftest import _make_auth_headers

# ── Coaching service ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_org_improvement_plan(db, monkeypatch):
    """Org improvement plan creates a coaching report with status=pending."""
    import json

    from app.services import ai_coaching

    async def _fake_call_ai(system_prompt, user_message, **kwargs):
        return json.dumps({
            "recommendations": [{"area": "Ops", "suggestion": "Improve", "priority": "high"}],
            "summary": "Test summary",
        })

    monkeypatch.setattr(ai_coaching, "_call_ai_safe", _fake_call_ai)

    # We need performance data — mock it
    from types import SimpleNamespace

    from app.services import performance as perf_service

    async def _fake_org_perf(db, org_id, days=30):
        return SimpleNamespace(
            total_employees=5, total_departments=2,
            avg_hours=7.5, avg_focus_ratio=0.6,
            avg_tasks_per_day=4.2,
            departments=[
                SimpleNamespace(department_name="Engineering", employee_count=3, avg_focus_ratio=0.7),
            ],
        )

    monkeypatch.setattr(perf_service, "get_org_performance", _fake_org_perf)

    result = await ai_coaching.generate_org_improvement_plan(db, org_id=1)
    assert result["report_id"] is not None
    assert result["status"] == "pending"
    assert len(result["recommendations"]) >= 1


@pytest.mark.asyncio
async def test_coaching_list_endpoint(client):
    headers = _make_auth_headers()
    r = await client.get("/api/v1/coaching", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_coaching_insights_endpoint(client):
    headers = _make_auth_headers()
    r = await client.get("/api/v1/coaching/insights", headers=headers)
    assert r.status_code == 200


# ── Weekly coaching job ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weekly_coaching_job_callable(db):
    """The weekly coaching job should be callable without crashing (may skip due to time)."""
    from app.jobs.intelligence import maybe_run_weekly_coaching

    # This will skip because it's likely not Monday 10 AM IST, but should not crash
    await maybe_run_weekly_coaching(db, org_id=1)


@pytest.mark.asyncio
async def test_weekly_coaching_in_scheduler_jobs():
    """Weekly coaching should be registered in the automation jobs list."""
    from app.services import sync_scheduler

    # Check the function alias exists
    assert hasattr(sync_scheduler, "_maybe_run_weekly_coaching")
    assert callable(sync_scheduler._maybe_run_weekly_coaching)
