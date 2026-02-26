"""E2E test: Draft plans -> List -> Approve -> Complete task.

Tests the full briefing lifecycle with monkeypatched AI calls.
"""
from unittest.mock import AsyncMock

from app.services import task_engine

# Deterministic AI response for task plans
_FAKE_AI_PLAN = (
    "TASK: Review PR #42 for auth module | PRIORITY: high | DETAILS: Check RBAC edge cases\n"
    "TASK: Fix login redirect bug | PRIORITY: high | DETAILS: Redirect loop on expired session\n"
    "TASK: Write unit tests for token refresh | PRIORITY: medium | DETAILS: Cover expired and revoked tokens\n"
    "REASON: Auth module is the current sprint focus and has open PRs."
)


async def _seed_team_member(client):
    """Create a team member so draft_team_plans has someone to plan for."""
    r = await client.post(
        "/api/v1/memory/team",
        json={"name": "Alice Dev", "role_title": "Developer", "team": "backend", "ai_level": 3},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def test_full_briefing_flow(client, monkeypatch):
    """Draft -> List -> Approve -> Complete task, end-to-end."""
    # Mock AI to avoid real API calls
    monkeypatch.setattr(task_engine, "call_ai", AsyncMock(return_value=_FAKE_AI_PLAN))
    monkeypatch.setattr(task_engine, "build_memory_context", AsyncMock(return_value="test context"))

    # 1. Seed a team member
    member_id = await _seed_team_member(client)
    assert member_id > 0

    # 2. DRAFT — POST /briefing/plans/draft
    r = await client.post("/api/v1/briefing/plans/draft")
    assert r.status_code == 200
    draft_body = r.json()
    assert draft_body["drafted"] >= 1
    plan_ids = draft_body["plan_ids"]
    assert len(plan_ids) >= 1

    # 3. LIST DRAFTS — GET /briefing/plans?status=draft
    r = await client.get("/api/v1/briefing/plans", params={"status": "draft"})
    assert r.status_code == 200
    plans = r.json()
    assert len(plans) >= 1
    plan = plans[0]
    assert plan["status"] == "draft"
    assert len(plan["tasks"]) == 3  # AI returned 3 TASK: lines
    assert plan["tasks"][0]["title"] == "Review PR #42 for auth module"
    assert plan["tasks"][0]["done"] is False
    assert plan["ai_reasoning"] == "Auth module is the current sprint focus and has open PRs."
    plan_id = plan["plan_id"]

    # 4. APPROVE — POST /briefing/plans/{plan_id}/approve
    r = await client.post(f"/api/v1/briefing/plans/{plan_id}/approve")
    assert r.status_code == 200
    approve_body = r.json()
    assert approve_body["status"] == "approved"
    assert approve_body["approved_at"] is not None

    # 5. Verify plan is now approved
    r = await client.get("/api/v1/briefing/plans", params={"status": "approved"})
    assert r.status_code == 200
    approved = r.json()
    assert any(p["plan_id"] == plan_id and p["status"] == "approved" for p in approved)

    # 6. COMPLETE TASK — POST /briefing/plans/{plan_id}/tasks/0/done
    r = await client.post(f"/api/v1/briefing/plans/{plan_id}/tasks/0/done")
    assert r.status_code == 200
    done_body = r.json()
    assert done_body["marked_done"] is True
    assert "1/3" in done_body["progress"]

    # 7. Complete second task
    r = await client.post(f"/api/v1/briefing/plans/{plan_id}/tasks/1/done")
    assert r.status_code == 200
    assert "2/3" in r.json()["progress"]

    # 8. DOUBLE APPROVE returns 404 (already approved)
    r = await client.post(f"/api/v1/briefing/plans/{plan_id}/approve")
    assert r.status_code == 404

    # 9. INVALID TASK INDEX returns 404
    r = await client.post(f"/api/v1/briefing/plans/{plan_id}/tasks/99/done")
    assert r.status_code == 404


async def test_draft_plans_skips_existing(client, monkeypatch):
    """Drafting again for the same day skips members who already have plans."""
    monkeypatch.setattr(task_engine, "call_ai", AsyncMock(return_value=_FAKE_AI_PLAN))
    monkeypatch.setattr(task_engine, "build_memory_context", AsyncMock(return_value=""))

    await _seed_team_member(client)

    # First draft
    r = await client.post("/api/v1/briefing/plans/draft")
    assert r.status_code == 200
    first_count = r.json()["drafted"]
    assert first_count >= 1

    # Second draft same day — should skip existing
    r = await client.post("/api/v1/briefing/plans/draft")
    assert r.status_code == 200
    assert r.json()["drafted"] == 0


async def test_team_dashboard_returns_summary(client):
    """GET /briefing/team returns team dashboard without AI."""
    r = await client.get("/api/v1/briefing/team")
    assert r.status_code == 200
    body = r.json()
    assert "summary" in body
    assert "team" in body
    assert "total_members" in body["summary"]


async def test_executive_briefing(client, monkeypatch):
    """GET /briefing/executive returns exec snapshot."""
    r = await client.get("/api/v1/briefing/executive")
    assert r.status_code == 200
    body = r.json()
    assert "summary" in body
    assert "calendar" in body
    assert "approvals" in body
    assert "inbox" in body
