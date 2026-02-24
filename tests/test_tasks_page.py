from app.core.security import create_access_token


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)


async def test_tasks_page_requires_login(client):
    response = await client.get("/web/tasks", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/web/login"


async def test_tasks_page_wires_shared_ui_utilities(client):
    _set_web_session(client)
    response = await client.get("/web/tasks")
    assert response.status_code == 200
    assert "/static/js/ui-utils.js" in response.text
    assert "mapUiError" in response.text
    assert "setButtonLoading" in response.text
