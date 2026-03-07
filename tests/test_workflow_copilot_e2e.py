"""Tests for the AI Workflow Copilot — planner, talk command, API, and handlers."""
from __future__ import annotations

import json

from app.core.security import create_access_token


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


def _staff_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1, "token_version": 1}
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "csrf-test-token")


# ── Planner: heuristic fallback ──────────────────────────────────────────────

async def test_planner_heuristic_email(monkeypatch):
    """Heuristic plan generates email steps when intent mentions email."""
    from app.engines.brain.workflow_planner import _heuristic_plan

    plan = _heuristic_plan(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Send a follow-up email to new leads",
        constraints={},
        available_integrations=["gmail"],
    )
    assert plan["name"]
    assert len(plan["steps"]) >= 2
    action_types = [s["action_type"] for s in plan["steps"]]
    assert "send_email" in action_types
    assert plan["confidence"] == 0.65


async def test_planner_heuristic_slack():
    from app.engines.brain.workflow_planner import _heuristic_plan

    plan = _heuristic_plan(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Post a weekly summary to Slack #general",
        constraints={},
        available_integrations=["slack"],
    )
    action_types = [s["action_type"] for s in plan["steps"]]
    assert "send_slack" in action_types


async def test_planner_heuristic_lead():
    from app.engines.brain.workflow_planner import _heuristic_plan

    plan = _heuristic_plan(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Assign and follow up with CRM leads",
        constraints={},
        available_integrations=[],
    )
    action_types = [s["action_type"] for s in plan["steps"]]
    assert "create_task" in action_types


async def test_planner_heuristic_generic():
    from app.engines.brain.workflow_planner import _heuristic_plan

    plan = _heuristic_plan(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Do something unexpected and novel",
        constraints={},
        available_integrations=[],
    )
    assert len(plan["steps"]) >= 1
    assert plan["steps"][0]["action_type"] == "ai_generate"


async def test_planner_heuristic_task():
    from app.engines.brain.workflow_planner import _heuristic_plan

    plan = _heuristic_plan(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Create a task for weekly report",
        constraints={},
        available_integrations=[],
    )
    action_types = [s["action_type"] for s in plan["steps"]]
    assert "create_task" in action_types


async def test_planner_heuristic_calendar():
    from app.engines.brain.workflow_planner import _heuristic_plan

    plan = _heuristic_plan(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Check my calendar and summarize meetings",
        constraints={},
        available_integrations=["calendar"],
    )
    action_types = [s["action_type"] for s in plan["steps"]]
    assert "fetch_calendar_digest" in action_types


# ── Planner: AI path with mock ──────────────────────────────────────────────

async def test_planner_ai_path(monkeypatch):
    """When AI returns valid JSON, it's used as the plan."""
    ai_response = json.dumps({
        "name": "Lead Triage",
        "summary": "Triage inbound leads",
        "trigger_mode": "manual",
        "risk_level": "medium",
        "steps": [
            {"key": "fetch", "name": "Fetch leads", "action_type": "fetch_calendar_digest", "params": {}, "requires_approval": False},
            {"key": "assign", "name": "Assign leads", "action_type": "assign_leads", "params": {"count": 5}, "requires_approval": True},
        ],
    })

    async def fake_call_ai(**kwargs):
        return ai_response

    monkeypatch.setattr("app.engines.brain.router.call_ai", fake_call_ai)

    from app.engines.brain.workflow_planner import generate_workflow_plan_draft

    plan = await generate_workflow_plan_draft(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Triage inbound leads",
        constraints={},
        available_integrations=["hubspot"],
    )
    assert plan["name"] == "Lead Triage"
    assert len(plan["steps"]) == 2
    assert plan["confidence"] == 0.85


async def test_planner_ai_falls_back_on_error(monkeypatch):
    """When AI call raises, falls back to heuristic."""
    async def broken_ai(**kwargs):
        raise RuntimeError("API down")

    monkeypatch.setattr("app.engines.brain.router.call_ai", broken_ai)

    from app.engines.brain.workflow_planner import generate_workflow_plan_draft

    plan = await generate_workflow_plan_draft(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Send email to leads",
        constraints={},
        available_integrations=[],
    )
    assert plan["confidence"] == 0.65  # heuristic confidence
    assert len(plan["steps"]) >= 1


async def test_planner_ai_sanitizes_unknown_action(monkeypatch):
    """Unknown action types from AI get replaced with noop."""
    ai_response = json.dumps({
        "name": "Test",
        "summary": "Test",
        "trigger_mode": "manual",
        "risk_level": "low",
        "steps": [
            {"key": "bad", "name": "Bad step", "action_type": "hack_the_planet", "params": {}, "requires_approval": False},
        ],
    })

    async def fake_call_ai(**kwargs):
        return ai_response

    monkeypatch.setattr("app.engines.brain.router.call_ai", fake_call_ai)

    from app.engines.brain.workflow_planner import generate_workflow_plan_draft

    plan = await generate_workflow_plan_draft(
        actor={"role": "CEO"},
        organization_id=1,
        workspace_id=None,
        intent="Test",
        constraints={},
        available_integrations=[],
    )
    assert plan["steps"][0]["action_type"] == "noop"


# ── Parse AI response ────────────────────────────────────────────────────────

def test_parse_ai_response_strips_markdown():
    from app.engines.brain.workflow_planner import _parse_ai_response

    raw = '```json\n{"name": "Test", "summary": "X", "steps": [{"key": "a", "name": "A", "action_type": "noop", "params": {}}]}\n```'
    result = _parse_ai_response(raw)
    assert result["name"] == "Test"
    assert len(result["steps"]) == 1


def test_parse_ai_response_rejects_no_steps():
    from app.engines.brain.workflow_planner import _parse_ai_response

    import pytest
    with pytest.raises(ValueError, match="missing 'steps'"):
        _parse_ai_response('{"name": "Bad"}')


# ── Handlers ─────────────────────────────────────────────────────────────────

def test_noop_handler():
    from app.services.execution_engine import HANDLERS

    result = HANDLERS["noop"]({})
    assert result == {"action": "noop"}


async def test_send_email_handler():
    from app.services.execution_engine import HANDLERS

    result = await HANDLERS["send_email"]({"to": "a@b.com", "subject": "Hi"})
    assert result["action"] == "send_email"
    assert result["to"] == "a@b.com"
    assert result["status"] == "drafted"


async def test_send_slack_handler():
    from app.services.execution_engine import HANDLERS

    result = await HANDLERS["send_slack"]({"channel": "#general", "message": "Hello"})
    assert result["action"] == "send_slack"
    assert result["channel"] == "#general"


def test_create_task_handler():
    from app.services.execution_engine import HANDLERS

    result = HANDLERS["create_task"]({"title": "Test task"})
    assert result["action"] == "create_task"
    assert result["title"] == "Test task"


async def test_ai_generate_handler(monkeypatch):
    from app.services.execution_engine import HANDLERS

    async def fake_call_ai(**kwargs):
        return "Generated text here"

    monkeypatch.setattr("app.engines.brain.router.call_ai", fake_call_ai)
    result = await HANDLERS["ai_generate"]({"prompt": "Summarize today"})
    assert result["action"] == "ai_generate"
    assert "Generated text" in result["output"]


# ── Talk command: build automation ────────────────────────────────────────────

async def test_talk_build_automation_command(client, monkeypatch):
    """'build automation ...' in Talk produces a workflow draft response."""
    _set_web_session(client)

    async def fake_copilot(**kwargs):
        return {
            "name": "Lead Follow-up",
            "summary": "Auto follow-up with leads",
            "trigger_mode": "manual",
            "steps": [
                {"key": "fetch", "name": "Fetch context", "action_type": "fetch_calendar_digest", "params": {}, "requires_approval": False},
                {"key": "email", "name": "Send email", "action_type": "send_email", "params": {}, "requires_approval": True},
            ],
            "risk_level": "medium",
            "confidence": 0.85,
        }

    monkeypatch.setattr("app.application.automation.copilot.generate_workflow_plan_draft", fake_copilot)
    monkeypatch.setattr("app.web.chat.run_agent", lambda **kw: (_ for _ in ()).throw(AssertionError("should not call AI")))

    resp = await client.post(
        "/web/agents/chat",
        data={"message": "build automation follow up with new leads every 3 days"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Lead Follow-up" in body["response"]
    assert "send_email" in body["response"]
    assert "needs approval" in body["response"].lower()


async def test_talk_build_automation_staff_denied(client, monkeypatch):
    """STAFF role cannot build automations."""
    token = create_access_token(
        {"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": 1, "token_version": 1}
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "csrf-test-token")

    monkeypatch.setattr("app.web.chat.run_agent", lambda **kw: (_ for _ in ()).throw(AssertionError("should not call AI")))

    resp = await client.post(
        "/web/agents/chat",
        data={"message": "build automation do something"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert resp.status_code == 200
    assert "requires MANAGER" in resp.json()["response"]


# ── API: copilot/plan ────────────────────────────────────────────────────────

async def test_api_copilot_plan(client, monkeypatch):
    async def fake_copilot(**kwargs):
        return {
            "name": "Test Plan",
            "summary": "Test summary",
            "trigger_mode": "manual",
            "steps": [{"key": "s1", "name": "Step 1", "action_type": "noop", "params": {}, "requires_approval": False}],
            "risk_level": "low",
            "confidence": 0.9,
        }

    monkeypatch.setattr("app.api.v1.endpoints.automation.build_workflow_copilot_plan", fake_copilot)
    from app.core.config import settings
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_COPILOT", True)

    resp = await client.post(
        "/api/v1/automations/copilot/plan",
        json={"intent": "Do a thing"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test Plan"
    assert len(body["steps"]) == 1


async def test_api_copilot_plan_staff_denied(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_COPILOT", True)

    resp = await client.post(
        "/api/v1/automations/copilot/plan",
        json={"intent": "Do a thing"},
        headers=_staff_headers(),
    )
    assert resp.status_code == 403


async def test_api_copilot_plan_disabled_returns_404(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_COPILOT", False)

    resp = await client.post(
        "/api/v1/automations/copilot/plan",
        json={"intent": "Do a thing"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 404


# ── API: copilot/plan-and-save ───────────────────────────────────────────────

async def test_api_copilot_plan_and_save(client, monkeypatch):
    async def fake_copilot(**kwargs):
        return {
            "name": "Saved Workflow",
            "summary": "A saved workflow",
            "trigger_mode": "manual",
            "steps": [
                {"key": "s1", "name": "Step 1", "action_type": "noop", "params": {}, "requires_approval": False},
                {"key": "s2", "name": "Step 2", "action_type": "create_task", "params": {"title": "Do it"}, "requires_approval": True},
            ],
            "risk_level": "medium",
            "confidence": 0.88,
        }

    monkeypatch.setattr("app.api.v1.endpoints.automation.build_workflow_copilot_plan", fake_copilot)
    from app.core.config import settings
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_COPILOT", True)
    monkeypatch.setattr(settings, "FEATURE_WORKFLOW_V2", True)

    resp = await client.post(
        "/api/v1/automations/copilot/plan-and-save",
        json={"intent": "Create a lead follow-up workflow"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Saved Workflow"
    assert body["status"] == "draft"
    assert body["id"] > 0
    assert len(body["steps_json"]) == 2


# ── Known action types ───────────────────────────────────────────────────────

def test_known_action_types_match_handlers():
    from app.engines.brain.workflow_planner import KNOWN_ACTION_TYPES
    from app.services.execution_engine import HANDLERS

    for action in KNOWN_ACTION_TYPES:
        if action == "unknown_noop":
            continue
        assert action in HANDLERS, f"{action} in KNOWN_ACTION_TYPES but not in HANDLERS"


# ── Risk level inference ─────────────────────────────────────────────────────

def test_infer_risk_level():
    from app.engines.brain.workflow_planner import _infer_risk_level

    assert _infer_risk_level([{"requires_approval": True}]) == "medium"
    assert _infer_risk_level([{"requires_approval": False}]) == "low"
    assert _infer_risk_level([]) == "low"
