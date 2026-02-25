from app.agents.orchestrator import AgentChatResponse
from app.core.security import create_access_token


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1,
         "token_version": 1, "purpose": "professional",
         "default_theme": "light", "default_avatar_mode": "professional"}
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "csrf-test-token")


async def test_web_chat_e2e_avatar_and_integration_command(client, monkeypatch):
    _set_web_session(client)

    async def fake_run_agent(*, request, **_kwargs):
        return AgentChatResponse(
            role="CEO Clone",
            response=f"mode={request.avatar_mode}",
            requires_approval=False,
            proposed_actions=[],
        )

    async def fake_github_status(*_args, **_kwargs):
        return {"connected": True, "last_sync_at": None, "login": "EmpireO", "repos_tracked": 3}

    monkeypatch.setattr("app.agents.orchestrator.run_agent", fake_run_agent)
    monkeypatch.setattr("app.services.github_service.get_github_status", fake_github_status)

    personal_msg = await client.post(
        "/web/agents/chat",
        data={"message": "hello", "avatar_mode": "personal"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert personal_msg.status_code == 200
    assert "mode=professional" in personal_msg.json()["response"]

    integration_msg = await client.post(
        "/web/agents/chat",
        data={"message": "check github status", "avatar_mode": "professional"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert integration_msg.status_code == 200
    assert "github" in integration_msg.json()["response"].lower()

    entertainment_msg = await client.post(
        "/web/agents/chat",
        data={"message": "give me a fun reel idea", "avatar_mode": "entertainment"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert entertainment_msg.status_code == 200

    personal_history = await client.get("/web/chat/history?avatar_mode=personal")
    professional_history = await client.get("/web/chat/history?avatar_mode=professional")
    entertainment_history = await client.get("/web/chat/history?avatar_mode=entertainment")
    assert personal_history.status_code == 200
    assert professional_history.status_code == 200
    assert entertainment_history.status_code == 200
    assert any("hello" in row["user_message"] for row in personal_history.json())
    assert any("check github status" in row["user_message"] for row in professional_history.json())
    assert any("fun reel idea" in row["user_message"] for row in entertainment_history.json())
