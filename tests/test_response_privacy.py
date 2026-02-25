from datetime import datetime, timezone

from app.core.config import settings
from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.event import Event


async def _insert_raw_event(payload_json: dict) -> None:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        session.add(
            Event(
                organization_id=1,
                event_type="legacy_event",
                actor_user_id=1,
                entity_type="integration",
                entity_id=1,
                payload_json=payload_json,
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    finally:
        await agen.aclose()


def _set_web_session(client) -> None:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )
    client.cookies.set("pc_session", token)


async def test_integrations_response_redacts_sensitive_config_fields(client):
    create_resp = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "gmail",
            "config_json": {
                "access_token": "ghp_very_secret",
                "api_key": "secret-key",
                "username": "founder@example.com",
            },
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["config_json"]["access_token"] == "***"
    assert body["config_json"]["api_key"] == "***"
    assert body["config_json"]["username"] == "f***@example.com"

    list_resp = await client.get("/api/v1/integrations")
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert rows
    assert rows[0]["config_json"]["access_token"] == "***"


async def test_ops_events_response_sanitizes_legacy_payloads(client):
    await _insert_raw_event(
        {
            "access_token": "legacy-secret-token",
            "email": "legacy@example.com",
            "reason": "daily_run_drafted",
        }
    )
    resp = await client.get("/api/v1/ops/events")
    assert resp.status_code == 200
    events = resp.json()
    legacy = next(item for item in events if item["event_type"] == "legacy_event")
    assert legacy["payload_json"]["access_token"] == "***"
    assert legacy["payload_json"]["email"] == "l***@example.com"
    assert legacy["payload_json"]["reason"] == "daily_run_drafted"


async def test_web_session_response_still_returns_principal_identity(client):
    _set_web_session(client)
    resp = await client.get("/web/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["logged_in"] is True
    assert body["user"]["email"] == "ceo@org1.com"


async def test_response_privacy_profile_strict_masks_pii(monkeypatch, client):
    monkeypatch.setattr(settings, "PRIVACY_POLICY_PROFILE", "strict", raising=False)
    create_resp = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "gmail",
            "config_json": {
                "username": "strict@example.com",
                "access_token": "ghp_very_secret",
            },
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["config_json"]["username"] == "s***@example.com"
    assert body["config_json"]["access_token"] == "***"


async def test_response_privacy_profile_debug_keeps_pii(monkeypatch, client):
    monkeypatch.setattr(settings, "PRIVACY_POLICY_PROFILE", "debug", raising=False)
    create_resp = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "gmail",
            "config_json": {
                "username": "debug@example.com",
                "access_token": "ghp_very_secret",
            },
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["config_json"]["username"] == "debug@example.com"
    assert body["config_json"]["access_token"] == "***"
