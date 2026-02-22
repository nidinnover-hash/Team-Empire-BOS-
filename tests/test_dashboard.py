from app.core.security import create_access_token


def _set_dashboard_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)


async def test_dashboard_returns_200(client):
    _set_dashboard_session(client)
    response = await client.get("/")
    assert response.status_code == 200


async def test_dashboard_returns_html(client):
    _set_dashboard_session(client)
    response = await client.get("/")
    assert "text/html" in response.headers["content-type"]


async def test_dashboard_contains_brand_name(client):
    _set_dashboard_session(client)
    response = await client.get("/")
    assert "Personal Clone" in response.text
    assert "Executive Briefing" in response.text
    assert "Generate Daily Run (Draft Only)" in response.text


async def test_dashboard_shows_empty_states(client):
    _set_dashboard_session(client)
    response = await client.get("/")
    assert "No commands yet" in response.text
    assert "No tasks yet" in response.text
    assert "No notes yet" in response.text


async def test_dashboard_shows_seeded_command(client):
    _set_dashboard_session(client)
    await client.post(
        "/api/v1/commands",
        json={"command_text": "Plan my week"},
    )
    response = await client.get("/")
    assert "Plan my week" in response.text


async def test_dashboard_shows_seeded_task(client):
    _set_dashboard_session(client)
    await client.post("/api/v1/tasks", json={"title": "Finish the backend"})
    response = await client.get("/")
    assert "Finish the backend" in response.text


async def test_dashboard_shows_seeded_note(client):
    _set_dashboard_session(client)
    await client.post("/api/v1/notes", json={"content": "Check emails at 9am"})
    response = await client.get("/")
    assert "Check emails at 9am" in response.text


async def test_dashboard_shows_task_done_badge(client):
    _set_dashboard_session(client)
    task_id = (
        await client.post("/api/v1/tasks", json={"title": "Ship v1"})
    ).json()["id"]
    await client.patch(f"/api/v1/tasks/{task_id}", json={"is_done": True})

    response = await client.get("/")
    assert "done" in response.text
