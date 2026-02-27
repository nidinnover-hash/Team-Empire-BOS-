from app.core.security import create_access_token


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "test-csrf")


async def test_talk_mode_redirects_when_not_logged_in(client):
    response = await client.get("/web/talk", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/web/login"


async def test_talk_mode_page_loads_for_logged_user(client):
    _set_web_session(client)
    response = await client.get("/web/talk")
    assert response.status_code == 200
    assert "Talk to Agent" in response.text
    assert "Continuous work conversation mode" in response.text
    assert "/static/js/ui-utils.js" in response.text
    assert "/static/js/talk-page.js" in response.text


async def test_talk_mode_bootstrap_returns_work_snapshot(client):
    _set_web_session(client)
    response = await client.get("/web/talk/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert "welcome" in body
    assert "snapshot" in body
    assert "learned_memory" in body
    assert "suggested_prompts" in body
    assert "open_tasks" in body["snapshot"]
    assert "pending_approvals" in body["snapshot"]
    assert "unread_emails" in body["snapshot"]


async def test_talk_mode_bootstrap_includes_learned_memory(client):
    _set_web_session(client)
    created = await client.post(
        "/api/v1/memory/profile",
        json={"key": "preference.general", "value": "concise updates", "category": "learned"},
    )
    assert created.status_code == 200

    response = await client.get("/web/talk/bootstrap")
    assert response.status_code == 200
    body = response.json()
    learned = body.get("learned_memory", [])
    assert any(item["key"] == "preference.general" for item in learned)
