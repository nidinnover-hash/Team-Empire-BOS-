from app.api.v1.endpoints import integrations as integrations_endpoint
from app.core.security import create_access_token


def _auth_headers(user_id: int, email: str, role: str, org_id: int) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def test_google_auth_url_and_oauth_callback_redacts_tokens(client, monkeypatch):
    monkeypatch.setattr(integrations_endpoint.settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(integrations_endpoint.settings, "GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setattr(integrations_endpoint.settings, "GOOGLE_REDIRECT_URI", "https://example.com/callback")

    async def fake_exchange_code_for_tokens(code: str, client_id: str, client_secret: str, redirect_uri: str):
        return {
            "access_token": "access-xyz",
            "refresh_token": "refresh-xyz",
            "token_type": "Bearer",
            "scope": "scope",
            "expires_in": 3600,
        }

    monkeypatch.setattr(
        integrations_endpoint,
        "exchange_code_for_tokens",
        fake_exchange_code_for_tokens,
    )

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    auth_url = await client.get("/api/v1/integrations/google-calendar/auth-url", headers=headers)
    assert auth_url.status_code == 200
    assert "accounts.google.com" in auth_url.json()["auth_url"]
    state = auth_url.json()["state"]

    callback = await client.post(
        "/api/v1/integrations/google-calendar/oauth/callback",
        json={"code": "abc", "state": state, "calendar_id": "primary"},
        headers=headers,
    )
    assert callback.status_code == 200
    body = callback.json()
    assert body["type"] == "google_calendar"
    assert body["config_json"]["access_token"] == "***"
    assert body["config_json"]["refresh_token"] == "***"


async def test_google_integration_test_provider_ping_success(client, monkeypatch):
    async def fake_list_events_for_day(access_token: str, day, calendar_id: str = "primary"):
        return []

    monkeypatch.setattr(integrations_endpoint, "list_events_for_day", fake_list_events_for_day)

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "google_calendar",
            "config_json": {"access_token": "access", "calendar_id": "primary"},
        },
        headers=headers,
    )
    assert connected.status_code == 201
    integration_id = connected.json()["id"]

    tested = await client.post(f"/api/v1/integrations/{integration_id}/test", headers=headers)
    assert tested.status_code == 200
    assert tested.json()["status"] == "ok"


async def test_google_integration_test_refresh_flow(client, monkeypatch):
    async def failing_list_events_for_day(access_token: str, day, calendar_id: str = "primary"):
        raise RuntimeError("expired token")

    async def fake_refresh_access_token(refresh_token: str, client_id: str, client_secret: str):
        return {"access_token": "new-access"}

    monkeypatch.setattr(integrations_endpoint, "list_events_for_day", failing_list_events_for_day)
    monkeypatch.setattr(integrations_endpoint, "refresh_access_token", fake_refresh_access_token)
    monkeypatch.setattr(integrations_endpoint.settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(integrations_endpoint.settings, "GOOGLE_CLIENT_SECRET", "csecret")

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "google_calendar",
            "config_json": {
                "access_token": "expired",
                "refresh_token": "refresh",
                "calendar_id": "primary",
            },
        },
        headers=headers,
    )
    assert connected.status_code == 201
    integration_id = connected.json()["id"]

    tested = await client.post(f"/api/v1/integrations/{integration_id}/test", headers=headers)
    assert tested.status_code == 200
    assert tested.json()["status"] == "ok"


async def test_google_integration_test_refresh_failure_is_sanitized(client, monkeypatch):
    async def failing_list_events_for_day(access_token: str, day, calendar_id: str = "primary"):
        raise RuntimeError("expired token")

    async def failing_refresh_access_token(refresh_token: str, client_id: str, client_secret: str):
        raise RuntimeError("invalid_grant: client_secret=super-secret")

    monkeypatch.setattr(integrations_endpoint, "list_events_for_day", failing_list_events_for_day)
    monkeypatch.setattr(integrations_endpoint, "refresh_access_token", failing_refresh_access_token)
    monkeypatch.setattr(integrations_endpoint.settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(integrations_endpoint.settings, "GOOGLE_CLIENT_SECRET", "csecret")

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "google_calendar",
            "config_json": {
                "access_token": "expired",
                "refresh_token": "refresh",
                "calendar_id": "primary",
            },
        },
        headers=headers,
    )
    assert connected.status_code == 201
    integration_id = connected.json()["id"]

    tested = await client.post(f"/api/v1/integrations/{integration_id}/test", headers=headers)
    assert tested.status_code == 200
    body = tested.json()
    assert body["status"] == "failed"
    assert "Google Calendar test failed after token refresh" in body["message"]
    assert "super-secret" not in body["message"]
