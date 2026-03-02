"""
Tests for orchestrator action extraction and multi-turn execution.

Covers:
- extract_proposed_actions() parses JSON from AI and returns ProposedAction list
- run_agent() now calls extract_proposed_actions (not hardcoded [])
- run_agent_multi_turn() decomposes complex requests into steps
- Multi-turn handles single-step fallback correctly
- Policy scoring is applied via the endpoint layer
"""
import json

from app.agents.orchestrator import (
    AgentChatRequest,
    AgentChatResponse,
    MultiTurnResponse,
    ProposedAction,
    StepResult,
    _decompose_plan,
    extract_proposed_actions,
    run_agent,
    run_agent_multi_turn,
)
from app.api.v1.endpoints import agents as agents_endpoint
from tests.conftest import _make_auth_headers

# ── extract_proposed_actions ─────────────────────────────────────────────────


async def test_extract_actions_returns_task_create(monkeypatch):
    """When AI returns a TASK_CREATE action, extract_proposed_actions parses it."""
    async def fake_call_ai(**kwargs):
        return json.dumps([{"action_type": "TASK_CREATE", "params": {"title": "Ship v2"}}])

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    actions = await extract_proposed_actions("Create task: Ship v2")
    assert len(actions) == 1
    assert actions[0].action_type == "TASK_CREATE"
    assert actions[0].params["title"] == "Ship v2"


async def test_extract_actions_returns_empty_on_bad_json(monkeypatch):
    """Malformed AI output falls back to empty list."""
    async def fake_call_ai(**kwargs):
        return "not valid json at all"

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    actions = await extract_proposed_actions("do something")
    assert actions == []


async def test_extract_actions_returns_empty_on_none_response(monkeypatch):
    async def fake_call_ai(**kwargs):
        return None

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    actions = await extract_proposed_actions("hello")
    assert actions == []


async def test_extract_actions_filters_non_dict_items(monkeypatch):
    async def fake_call_ai(**kwargs):
        return json.dumps([{"action_type": "EMAIL_DRAFT", "params": {}}, "bad", 42])

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    actions = await extract_proposed_actions("draft email")
    assert len(actions) == 1
    assert actions[0].action_type == "EMAIL_DRAFT"


async def test_extract_actions_multiple(monkeypatch):
    async def fake_call_ai(**kwargs):
        return json.dumps([
            {"action_type": "TASK_CREATE", "params": {"title": "Task A"}},
            {"action_type": "MEMORY_WRITE", "params": {"key": "pref", "value": "dark mode"}},
        ])

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    actions = await extract_proposed_actions("create task and remember preference")
    assert len(actions) == 2
    assert {a.action_type for a in actions} == {"TASK_CREATE", "MEMORY_WRITE"}


# ── run_agent with action extraction ────────────────────────────────────────


async def test_run_agent_calls_extract_actions(monkeypatch):
    """run_agent() now populates proposed_actions via extract_proposed_actions."""
    call_count = 0

    async def fake_call_ai(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Main response
            return "I'll help you create that task."
        # Intent extraction
        return json.dumps([{"action_type": "TASK_CREATE", "params": {"title": "Test"}}])

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    result = await run_agent(
        AgentChatRequest(message="Create task: Test something"),
    )
    assert isinstance(result, AgentChatResponse)
    assert len(result.proposed_actions) == 1
    assert result.proposed_actions[0].action_type == "TASK_CREATE"
    assert call_count == 2  # main call + intent extraction call


async def test_run_agent_filters_none_actions(monkeypatch):
    """NONE actions are filtered out of the response."""
    call_count = 0

    async def fake_call_ai(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "Here is my analysis."
        return json.dumps([{"action_type": "NONE", "params": {}}])

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    result = await run_agent(AgentChatRequest(message="What should I do today?"))
    assert result.proposed_actions == []


# ── _decompose_plan ──────────────────────────────────────────────────────────


async def test_decompose_plan_returns_steps(monkeypatch):
    async def fake_call_ai(**kwargs):
        return json.dumps([
            {"step": 1, "description": "Check calendar", "force_role": "Ops Manager Clone"},
            {"step": 2, "description": "Draft agenda email", "force_role": "CEO Clone"},
        ])

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    plan = await _decompose_plan("Schedule a meeting and email the agenda")
    assert len(plan) == 2
    assert plan[0]["description"] == "Check calendar"
    assert plan[1]["force_role"] == "CEO Clone"


async def test_decompose_plan_fallback_on_bad_json(monkeypatch):
    async def fake_call_ai(**kwargs):
        return "I can't parse this"

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    plan = await _decompose_plan("do complex thing")
    assert len(plan) == 1
    assert plan[0]["description"] == "do complex thing"


async def test_decompose_plan_caps_at_5_steps(monkeypatch):
    async def fake_call_ai(**kwargs):
        return json.dumps([{"step": i, "description": f"Step {i}", "force_role": None} for i in range(10)])

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    plan = await _decompose_plan("very complex request")
    assert len(plan) == 5


# ── run_agent_multi_turn ─────────────────────────────────────────────────────


async def test_multi_turn_single_step_fallback(monkeypatch):
    """Single-step plan wraps into MultiTurnResponse correctly."""
    call_count = 0

    async def fake_call_ai(**kwargs):
        nonlocal call_count
        call_count += 1
        system = kwargs.get("system_prompt", "")
        if "task planner" in system.lower():
            return json.dumps([{"step": 1, "description": "Simple request", "force_role": None}])
        if "intent classifier" in system.lower():
            return json.dumps([{"action_type": "NONE", "params": {}}])
        return "Here is a simple response."

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    result = await run_agent_multi_turn(
        AgentChatRequest(message="What is the status?"),
    )
    assert isinstance(result, MultiTurnResponse)
    assert result.total_steps == 1
    assert len(result.steps) == 1
    assert result.steps[0].step_number == 1


async def test_multi_turn_multi_step(monkeypatch):
    """Multi-step plan executes each step sequentially."""
    call_count = 0

    async def fake_call_ai(**kwargs):
        nonlocal call_count
        call_count += 1
        system = kwargs.get("system_prompt", "")
        if "task planner" in system.lower():
            return json.dumps([
                {"step": 1, "description": "Analyze team status", "force_role": "Ops Manager Clone"},
                {"step": 2, "description": "Send summary to CEO", "force_role": "CEO Clone"},
            ])
        if "intent classifier" in system.lower():
            return json.dumps([{"action_type": "NONE", "params": {}}])
        return f"Step response #{call_count}"

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    result = await run_agent_multi_turn(
        AgentChatRequest(message="Analyze team and send summary to CEO"),
    )
    assert result.total_steps == 2
    assert len(result.steps) == 2
    assert result.steps[0].role == "Ops Manager Clone"
    assert result.steps[1].role == "CEO Clone"


async def test_multi_turn_accumulates_approval_count(monkeypatch):
    """Steps with risky tokens get requires_approval=True and count is tracked."""
    call_count = 0

    async def fake_call_ai(**kwargs):
        nonlocal call_count
        call_count += 1
        system = kwargs.get("system_prompt", "")
        if "task planner" in system.lower():
            return json.dumps([
                {"step": 1, "description": "Review report", "force_role": None},
                {"step": 2, "description": "Send report to client", "force_role": None},
            ])
        if "intent classifier" in system.lower():
            return json.dumps([{"action_type": "NONE", "params": {}}])
        return "Done"

    monkeypatch.setattr("app.agents.orchestrator.call_ai", fake_call_ai)

    result = await run_agent_multi_turn(
        AgentChatRequest(message="Review and send report"),
    )
    # "send" is a risky token, step 2 should require approval
    assert result.steps_requiring_approval >= 1


# ── API endpoint integration ─────────────────────────────────────────────────


async def test_multi_turn_endpoint_returns_200(client, monkeypatch):
    """POST /api/v1/agents/multi-turn returns 200 with valid response shape."""
    async def _fake_multi_turn(*_args, **_kwargs):
        return MultiTurnResponse(
            steps=[StepResult(
                step_number=1,
                description="Test step",
                role="CEO Clone",
                response="Done.",
                requires_approval=False,
            )],
            final_summary="Done.",
            total_steps=1,
            steps_requiring_approval=0,
            all_proposed_actions=[],
            confidence_score=70,
            confidence_level="medium",
            needs_human_review=False,
        )

    monkeypatch.setattr(agents_endpoint, "run_agent_multi_turn", _fake_multi_turn)

    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    response = await client.post(
        "/api/v1/agents/multi-turn",
        json={"message": "What should I focus on?"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_steps"] == 1
    assert len(data["steps"]) == 1
    assert data["steps"][0]["role"] == "CEO Clone"


async def test_multi_turn_endpoint_blocked_for_staff(client, monkeypatch):
    """STAFF cannot access multi-turn endpoint (CEO/ADMIN/MANAGER only)."""
    headers = _make_auth_headers(4, "staff@org1.com", "STAFF", 1)
    response = await client.post(
        "/api/v1/agents/multi-turn",
        json={"message": "Do complex thing"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_chat_endpoint_now_returns_actions(client, monkeypatch):
    """POST /api/v1/agents/chat returns populated proposed_actions."""
    async def _fake_run_agent(*_args, **_kwargs):
        return AgentChatResponse(
            role="CEO Clone",
            response="I'll create that task.",
            requires_approval=False,
            proposed_actions=[
                ProposedAction(action_type="TASK_CREATE", params={"title": "Test task"}),
            ],
        )

    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent)

    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    response = await client.post(
        "/api/v1/agents/chat",
        json={"message": "Create task: Test task"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["proposed_actions"]) == 1
    assert data["proposed_actions"][0]["action_type"] == "TASK_CREATE"
    assert data["policy_score"] <= 100
