"""
Tests for TASK_CREATE and EMAIL_DRAFT agent action execution.

Guards:
- TASK_CREATE fires only when user message contains "create task" / "add task" / "make task"
- EMAIL_DRAFT fires only when user message contains "draft reply" / "draft email" etc.
- Both are gated by role (TASK_CREATE: CEO/ADMIN/MANAGER; EMAIL_DRAFT: CEO/ADMIN)
- Neither fires on a plain chat message without the trigger phrase
"""
from app.agents.orchestrator import AgentChatResponse, ProposedAction
from app.api.v1.endpoints import agents as agents_endpoint
from app.core.security import create_access_token
from app.services import email_service as real_email_service


def _auth_headers(user_id: int, email: str, role: str, org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


# ── Fake orchestrator responses ───────────────────────────────────────────────

async def _fake_run_agent_task(*_args, **_kwargs) -> AgentChatResponse:
    return AgentChatResponse(
        role="Ops Manager Clone",
        response="I'll create that task for you.",
        requires_approval=False,
        proposed_actions=[
            ProposedAction(
                action_type="TASK_CREATE",
                params={"title": "Review quarterly report"},
            )
        ],
    )


async def _fake_run_agent_email_draft(*_args, **_kwargs) -> AgentChatResponse:
    return AgentChatResponse(
        role="CEO Clone",
        response="I'll draft a reply to that email.",
        requires_approval=True,
        proposed_actions=[
            ProposedAction(
                action_type="EMAIL_DRAFT",
                params={"email_id": 1},
            )
        ],
    )


async def _fake_run_agent_none(*_args, **_kwargs) -> AgentChatResponse:
    return AgentChatResponse(
        role="CEO Clone",
        response="Here is my analysis.",
        requires_approval=False,
        proposed_actions=[ProposedAction(action_type="TASK_CREATE", params={"title": "Shadow task"})],
    )


# ── TASK_CREATE tests ─────────────────────────────────────────────────────────

async def test_agent_creates_task_when_triggered(client, monkeypatch):
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent_task)

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    response = await client.post(
        "/api/v1/agents/chat",
        json={"message": "Create task: Review quarterly report"},
        headers=headers,
    )
    assert response.status_code == 200

    tasks = await client.get("/api/v1/tasks", headers=headers)
    assert tasks.status_code == 200
    titles = [t["title"] for t in tasks.json()]
    assert "Review quarterly report" in titles


async def test_agent_task_creation_is_audited(client, monkeypatch):
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent_task)

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    await client.post(
        "/api/v1/agents/chat",
        json={"message": "Add task for me"},
        headers=headers,
    )

    events = await client.get("/api/v1/ops/events", headers=headers)
    assert events.status_code == 200
    assert any(e["event_type"] == "agent_task_created" for e in events.json())


async def test_agent_does_not_create_task_without_trigger(client, monkeypatch):
    """A TASK_CREATE proposed_action must not fire on a plain chat message."""
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent_none)

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    await client.post(
        "/api/v1/agents/chat",
        json={"message": "What should I focus on today?"},
        headers=headers,
    )

    tasks = await client.get("/api/v1/tasks", headers=headers)
    assert tasks.status_code == 200
    assert tasks.json() == []


async def test_agent_task_create_blocked_for_staff(client, monkeypatch):
    """STAFF role must not be able to trigger TASK_CREATE."""
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent_task)

    headers = _auth_headers(2, "staff@org.com", "STAFF", 1)
    await client.post(
        "/api/v1/agents/chat",
        json={"message": "Create task: do something"},
        headers=headers,
    )

    # STAFF can view tasks (may need CEO token to check)
    ceo_headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    tasks = await client.get("/api/v1/tasks", headers=ceo_headers)
    assert tasks.json() == []


# ── EMAIL_DRAFT tests ─────────────────────────────────────────────────────────

async def test_agent_drafts_email_when_triggered(client, monkeypatch):
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent_email_draft)

    # Stub draft_reply so we don't need a real email row
    async def fake_draft_reply(db, email_id, org_id, actor_user_id, instruction=""):
        return "Dear sender, thank you for your message."

    monkeypatch.setattr(real_email_service, "draft_reply", fake_draft_reply)
    # Also patch the reference in the agents module
    monkeypatch.setattr(agents_endpoint.email_service, "draft_reply", fake_draft_reply)

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    response = await client.post(
        "/api/v1/agents/chat",
        json={"message": "Draft reply to email 1"},
        headers=headers,
    )
    assert response.status_code == 200

    events = await client.get("/api/v1/ops/events", headers=headers)
    assert any(e["event_type"] == "agent_email_draft_created" for e in events.json())


async def test_agent_does_not_draft_email_without_trigger(client, monkeypatch):
    """EMAIL_DRAFT proposed_action must not fire unless user asks for a draft."""
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent_email_draft)

    draft_called = False

    async def spy_draft_reply(*_args, **_kwargs):
        nonlocal draft_called
        draft_called = True
        return "Draft"

    monkeypatch.setattr(agents_endpoint.email_service, "draft_reply", spy_draft_reply)

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    await client.post(
        "/api/v1/agents/chat",
        json={"message": "Tell me about email best practices"},
        headers=headers,
    )
    assert not draft_called


async def test_agent_email_draft_blocked_for_manager(client, monkeypatch):
    """MANAGER role must not trigger EMAIL_DRAFT (CEO/ADMIN only)."""
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent_email_draft)

    draft_called = False

    async def spy_draft_reply(*_args, **_kwargs):
        nonlocal draft_called
        draft_called = True
        return "Draft"

    monkeypatch.setattr(agents_endpoint.email_service, "draft_reply", spy_draft_reply)

    headers = _auth_headers(3, "mgr@org.com", "MANAGER", 1)
    await client.post(
        "/api/v1/agents/chat",
        json={"message": "Draft reply to email 1"},
        headers=headers,
    )
    assert not draft_called
