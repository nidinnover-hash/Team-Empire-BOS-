from sqlalchemy import text

from app.agents.orchestrator import AgentChatResponse
from app.core.deps import get_db
from app.core.security import create_access_token, decode_access_token
from app.main import app as fastapi_app


def _set_web_session(client) -> None:
    token = create_access_token(
        {
            "id": 1,
            "email": "ceo@org1.com",
            "role": "CEO",
            "org_id": 1,
            "purpose": "professional",
            "default_theme": "light",
            "default_avatar_mode": "professional",
        }
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "csrf-test-token")


async def test_web_chat_avatar_mode_is_forwarded(client, monkeypatch):
    _set_web_session(client)

    async def fake_run_agent(*, request, **_kwargs):
        return AgentChatResponse(
            role="CEO Clone",
            response=f"avatar={request.avatar_mode}",
            requires_approval=False,
            proposed_actions=[],
        )

    monkeypatch.setattr("app.web.chat.run_agent", fake_run_agent)

    response = await client.post(
        "/web/agents/chat",
        data={"message": "hello", "avatar_mode": "personal"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert response.status_code == 200
    assert "avatar=professional" in response.json()["response"]


async def test_web_chat_history_isolated_by_avatar_mode(client, monkeypatch):
    _set_web_session(client)

    async def fake_run_agent(*, request, **_kwargs):
        return AgentChatResponse(
            role="CEO Clone",
            response=f"mode={request.avatar_mode}",
            requires_approval=False,
            proposed_actions=[],
        )

    monkeypatch.setattr("app.web.chat.run_agent", fake_run_agent)

    await client.post(
        "/web/agents/chat",
        data={"message": "personal one", "avatar_mode": "personal"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    await client.post(
        "/web/agents/chat",
        data={"message": "professional one", "avatar_mode": "professional"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    personal_hist = await client.get("/web/chat/history?avatar_mode=personal")
    professional_hist = await client.get("/web/chat/history?avatar_mode=professional")
    assert personal_hist.status_code == 200
    assert professional_hist.status_code == 200
    assert any("personal one" in item["user_message"] for item in personal_hist.json())
    # Professional-purpose sessions are pinned to professional lane.
    assert any("professional one" in item["user_message"] for item in personal_hist.json())
    assert any("professional one" in item["user_message"] for item in professional_hist.json())


async def test_web_chat_injects_only_matching_avatar_memory(client, monkeypatch):
    _set_web_session(client)

    async def fake_run_agent(*, memory_context, **_kwargs):
        marker = "has_personal_memory" if "favorite_style: warm" in memory_context else "no_personal_memory"
        return AgentChatResponse(
            role="CEO Clone",
            response=marker,
            requires_approval=False,
            proposed_actions=[],
        )

    monkeypatch.setattr("app.web.chat.run_agent", fake_run_agent)

    # Seed avatar-scoped memory directly.
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        await session.execute(
            text(
                """
            INSERT INTO avatar_memory (organization_id, avatar_mode, key, value, created_at, updated_at)
            VALUES (1, 'personal', 'favorite_style', 'warm', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
            )
        )
        await session.commit()
    finally:
        await agen.aclose()

    personal = await client.post(
        "/web/agents/chat",
        data={"message": "hello", "avatar_mode": "personal"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    professional = await client.post(
        "/web/agents/chat",
        data={"message": "hello", "avatar_mode": "professional"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert personal.status_code == 200
    assert professional.status_code == 200
    assert personal.json()["response"] == "no_personal_memory"
    assert professional.json()["response"] == "no_personal_memory"


async def test_personal_login_can_read_professional_but_writes_personal_lane(client, monkeypatch):
    _set_web_session(client)

    async def fake_run_agent(*, request, **_kwargs):
        return AgentChatResponse(
            role="CEO Clone",
            response=f"mode={request.avatar_mode}",
            requires_approval=False,
            proposed_actions=[],
        )

    monkeypatch.setattr("app.web.chat.run_agent", fake_run_agent)

    # Force a personal-purpose login token.
    token = create_access_token(
        {
            "id": 5,
            "email": "nidinnover@gmail.com",
            "role": "CEO",
            "org_id": 1,
            "purpose": "personal",
            "default_theme": "dark",
            "default_avatar_mode": "personal",
        }
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "csrf-test-token")

    # Personal account requests professional read lane.
    response = await client.post(
        "/web/agents/chat",
        data={"message": "hello from personal", "avatar_mode": "professional"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert response.status_code == 200
    assert "mode=professional" in response.json()["response"]

    # Message should be written only in personal lane.
    personal_history = await client.get("/web/chat/history?avatar_mode=personal")
    professional_history = await client.get("/web/chat/history?avatar_mode=professional")
    assert any("hello from personal" in row["user_message"] for row in personal_history.json())
    assert not any("hello from personal" in row["user_message"] for row in professional_history.json())


async def test_web_api_token_preserves_purpose_claims(client):
    personal_token = create_access_token(
        {
            "id": 5,
            "email": "nidinnover@gmail.com",
            "role": "CEO",
            "org_id": 1,
            "purpose": "personal",
            "default_theme": "dark",
            "default_avatar_mode": "personal",
        }
    )
    client.cookies.set("pc_session", personal_token)

    refreshed = await client.get("/web/api-token")
    assert refreshed.status_code == 200
    payload = decode_access_token(refreshed.json()["token"])
    assert payload.get("purpose") == "personal"
    assert payload.get("default_theme") == "dark"
    assert payload.get("default_avatar_mode") == "personal"
