from datetime import date

from app.core.security import create_access_token


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)
    client.cookies.set("pc_csrf", "csrf-test-token")


async def test_web_chat_handles_github_status_command(client, monkeypatch):
    _set_web_session(client)

    async def fake_status(*_args, **_kwargs):
        return {"connected": True, "last_sync_at": "2026-02-24T09:00:00+00:00", "login": "EmpireO", "repos_tracked": 7}

    async def should_not_call_ai(*_args, **_kwargs):
        raise AssertionError("run_agent should not be called for integration command")

    monkeypatch.setattr("app.services.github_service.get_github_status", fake_status)
    monkeypatch.setattr("app.web.chat.run_agent", should_not_call_ai)

    response = await client.post(
        "/web/agents/chat",
        data={"message": "check github status"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "Ops Manager Clone"
    assert "github" in body["response"].lower()
    assert "connected" in body["response"].lower()


async def test_web_chat_can_create_task_from_talk_command(client, monkeypatch):
    _set_web_session(client)

    async def should_not_call_ai(*_args, **_kwargs):
        raise AssertionError("run_agent should not be called for create task command")

    monkeypatch.setattr("app.web.chat.run_agent", should_not_call_ai)

    response = await client.post(
        "/web/agents/chat",
        data={"message": "create task Prepare integration audit"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert response.status_code == 200
    assert "Task created:" in response.json()["response"]

    tasks = await client.get("/api/v1/tasks")
    assert tasks.status_code == 200
    assert any("Prepare integration audit" in t["title"] for t in tasks.json())


async def test_web_chat_expense_tracker_summary(client, monkeypatch):
    _set_web_session(client)

    async def should_not_call_ai(*_args, **_kwargs):
        raise AssertionError("run_agent should not be called for expense tracker command")

    monkeypatch.setattr("app.web.chat.run_agent", should_not_call_ai)

    await client.post(
        "/api/v1/finance",
        json={
            "type": "income",
            "amount": 5000,
            "category": "sales",
            "description": "monthly revenue",
            "entry_date": str(date.today()),
        },
    )
    await client.post(
        "/api/v1/finance",
        json={
            "type": "expense",
            "amount": 1200,
            "category": "software",
            "description": "api spend",
            "entry_date": str(date.today()),
        },
    )

    response = await client.post(
        "/web/agents/chat",
        data={"message": "show api expense tracker summary"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )
    assert response.status_code == 200
    text = response.json()["response"].lower()
    assert "expense tracker" in text
    assert "efficiency_score" in text
