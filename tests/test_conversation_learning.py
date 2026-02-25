from app.agents.orchestrator import AgentChatResponse
from app.core.security import create_access_token
from app.services import conversation_learning as learning_service


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "csrf-test-token")


def test_extract_learning_signals_parses_preferences():
    signals = learning_service.extract_learning_signals(
        "Call me Nidin. I prefer concise updates. My top priority is sales growth."
    )
    kv = {s.key: s.value for s in signals}
    assert kv["identity.preferred_name"] == "Nidin"
    assert kv["preference.general"] == "concise updates"
    assert kv["work.priority_focus"] == "sales growth"


def test_extract_learning_signals_ignores_sensitive_text():
    signals = learning_service.extract_learning_signals("Remember my password is 1234.")
    assert signals == []


async def test_web_chat_auto_learns_preference_memory(client, monkeypatch):
    _set_web_session(client)

    async def fake_run_agent(*_args, **_kwargs):
        return AgentChatResponse(
            role="CEO Clone",
            response="Noted.",
            requires_approval=False,
            proposed_actions=[],
        )

    monkeypatch.setattr("app.agents.orchestrator.run_agent", fake_run_agent)

    r = await client.post(
        "/web/agents/chat",
        data={"message": "I prefer daily summaries at 8am."},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert r.status_code == 200

    profile = await client.get("/api/v1/memory/profile")
    assert profile.status_code == 200
    items = profile.json()
    assert any(
        item["key"] == "preference.general"
        and item["value"] == "daily summaries at 8am"
        for item in items
    )
