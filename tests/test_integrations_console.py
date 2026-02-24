from app.core.security import create_access_token


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)


async def test_integrations_console_redirects_when_not_logged_in(client):
    response = await client.get("/web/integrations", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/web/login"


async def test_integrations_console_returns_200_and_branding(client):
    _set_web_session(client)
    response = await client.get("/web/integrations")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Integration Control Center" in response.text
    assert "Connect Gmail OAuth" in response.text
    assert "gmail-health-alert" in response.text
    assert "/static/js/api-client.js" in response.text
    assert "/static/js/ui-utils.js" in response.text
    assert "startAbortableRequest" in response.text
    assert "confirmDanger" in response.text
    assert "health-badge" in response.text
    assert "stale 24h+" in response.text
