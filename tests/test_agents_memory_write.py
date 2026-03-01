from app.agents.orchestrator import AgentChatResponse, ProposedAction
from app.api.v1.endpoints import agents as agents_endpoint
from tests.conftest import _make_auth_headers


async def _fake_run_agent(*_args, **_kwargs) -> AgentChatResponse:
    return AgentChatResponse(
        role="CEO Clone",
        response="Captured.",
        requires_approval=False,
        proposed_actions=[
            ProposedAction(
                action_type="MEMORY_WRITE",
                params={"key": "communication_style", "value": "Be concise"},
            )
        ],
    )


async def _fake_run_agent_no_memory(*_args, **_kwargs) -> AgentChatResponse:
    return AgentChatResponse(
        role="CEO Clone",
        response="No memory action.",
        requires_approval=False,
        proposed_actions=[ProposedAction(action_type="NONE", params={})],
    )


async def test_agent_chat_does_not_write_memory_without_remember(client, monkeypatch):
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent)

    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    response = await client.post(
        "/api/v1/agents/chat",
        json={"message": "Set my communication style as concise."},
        headers=headers,
    )
    assert response.status_code == 200

    profile = await client.get("/api/v1/memory/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json() == []


async def test_agent_chat_writes_memory_when_message_says_remember(client, monkeypatch):
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent)

    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    response = await client.post(
        "/api/v1/agents/chat",
        json={"message": "Remember this: my communication style is concise."},
        headers=headers,
    )
    assert response.status_code == 200

    profile = await client.get("/api/v1/memory/profile", headers=headers)
    assert profile.status_code == 200
    items = profile.json()
    # Check the explicitly written memory key (auto-learning may add extra entries)
    comm_entry = next((i for i in items if i["key"] == "communication_style"), None)
    assert comm_entry is not None, f"communication_style not found in {[i['key'] for i in items]}"
    assert comm_entry["value"] == "Be concise"

    events = await client.get("/api/v1/ops/events", headers=headers)
    assert events.status_code == 200
    assert any(item["event_type"] == "agent_memory_written" for item in events.json())


async def test_agent_chat_logs_memory_write_skipped_when_no_valid_action(client, monkeypatch):
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent_no_memory)

    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    response = await client.post(
        "/api/v1/agents/chat",
        json={"message": "Remember this for me."},
        headers=headers,
    )
    assert response.status_code == 200

    events = await client.get("/api/v1/ops/events", headers=headers)
    assert events.status_code == 200
    assert any(item["event_type"] == "agent_memory_write_skipped" for item in events.json())


async def test_agent_policy_blocks_secret_memory_write(client, monkeypatch):
    monkeypatch.setattr(agents_endpoint, "run_agent", _fake_run_agent)

    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    response = await client.post(
        "/api/v1/agents/chat",
        json={"message": "Remember this: my API key token is super-secret."},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["blocked_by_policy"] is True
    assert "MEMORY_WRITE" in payload["policy_blocked_actions"]

    profile = await client.get("/api/v1/memory/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json() == []
