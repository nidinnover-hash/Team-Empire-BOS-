from app.api.v1.endpoints import email as email_endpoint
from app.core.deps import get_db
from app.main import app as fastapi_app
from app.services.integration import get_integration_by_type
from tests.conftest import _make_auth_headers


async def test_gmail_callback_keeps_existing_refresh_token_when_missing(client, monkeypatch):
    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)

    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "gmail",
            "config_json": {
                "access_token": "old-access",
                "refresh_token": "old-refresh",
                "expires_at": "2026-02-22T12:00:00+00:00",
            },
        },
        headers=headers,
    )
    assert connected.status_code == 201

    def fake_exchange_code_for_tokens(_code: str) -> dict:
        return {
            "access_token": "new-access",
            # Intentionally missing refresh_token (real Google behavior on repeat consent)
            "expires_at": "2026-02-22T13:00:00+00:00",
        }

    monkeypatch.setattr(email_endpoint, "exchange_code_for_tokens", fake_exchange_code_for_tokens)

    state = email_endpoint._sign_email_state(1)
    callback = await client.get(
        f"/api/v1/email/callback?code=fake-code&state={state}",
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "/web/integrations?gmail=connected" in callback.headers["location"]

    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        integration = await get_integration_by_type(session, 1, "gmail")
        assert integration is not None
        cfg = integration.config_json
    finally:
        await agen.aclose()

    assert cfg["access_token"] == "new-access"
    assert cfg["refresh_token"] == "old-refresh"


async def test_gmail_callback_sanitizes_oauth_error_detail(client, monkeypatch):
    def fake_exchange_code_for_tokens(_code: str) -> dict:
        return {"error": "invalid_grant: client_secret=super-secret"}

    monkeypatch.setattr(email_endpoint, "exchange_code_for_tokens", fake_exchange_code_for_tokens)

    state = email_endpoint._sign_email_state(1)
    callback = await client.get(f"/api/v1/email/callback?code=fake-code&state={state}")
    assert callback.status_code == 400
    detail = callback.json()["detail"]
    assert "OAuth failed" in detail
    assert "super-secret" not in detail
