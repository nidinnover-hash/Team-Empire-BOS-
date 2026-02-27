"""
Tests for Slack integration endpoints.

All Slack API calls are mocked so no real bot token is required.
"""
from app.core.security import create_access_token
from app.services import slack_service


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


_DISCONNECTED = {"connected": False, "last_sync_at": None, "team": None, "channels_tracked": None}
_CONNECTED = {"connected": True, "last_sync_at": "2026-02-23T10:00:00Z", "team": "Nidin AI", "channels_tracked": 3}


# ── POST /api/v1/integrations/slack/connect ───────────────────────────────────

async def test_slack_connect_success(client, monkeypatch):
    async def _fake_connect(db, org_id, bot_token):
        return {"id": 1, "status": "connected", "team": "Nidin AI"}

    monkeypatch.setattr(slack_service, "connect_slack", _fake_connect)

    response = await client.post(
        "/api/v1/integrations/slack/connect",
        json={"bot_token": "xoxb-XXXX-YYYY"},
        headers=_ceo_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["connected"] is True
    assert body["team"] == "Nidin AI"


async def test_slack_connect_bad_token_returns_400(client, monkeypatch):
    async def _fake_connect_fail(db, org_id, bot_token):
        raise ValueError("invalid_auth")

    monkeypatch.setattr(slack_service, "connect_slack", _fake_connect_fail)

    response = await client.post(
        "/api/v1/integrations/slack/connect",
        json={"bot_token": "bad"},
        headers=_ceo_headers(),
    )
    assert response.status_code == 400


async def test_slack_connect_denied_for_staff(client):
    staff = create_access_token({"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": 1, "token_version": 1})
    response = await client.post(
        "/api/v1/integrations/slack/connect",
        json={"bot_token": "xoxb-anything"},
        headers={"Authorization": f"Bearer {staff}"},
    )
    assert response.status_code == 403


async def test_slack_connect_missing_token_returns_422(client):
    response = await client.post(
        "/api/v1/integrations/slack/connect",
        json={},
        headers=_ceo_headers(),
    )
    assert response.status_code == 422


# ── GET /api/v1/integrations/slack/status ────────────────────────────────────

async def test_slack_status_not_connected(client, monkeypatch):
    async def _status(db, org_id):
        return _DISCONNECTED

    monkeypatch.setattr(slack_service, "get_slack_status", _status)

    response = await client.get("/api/v1/integrations/slack/status", headers=_ceo_headers())
    assert response.status_code == 200
    assert response.json()["connected"] is False


async def test_slack_status_connected(client, monkeypatch):
    async def _status(db, org_id):
        return _CONNECTED

    monkeypatch.setattr(slack_service, "get_slack_status", _status)

    body = (await client.get("/api/v1/integrations/slack/status", headers=_ceo_headers())).json()
    assert body["connected"] is True
    assert body["team"] == "Nidin AI"
    assert body["channels_tracked"] == 3


# ── POST /api/v1/integrations/slack/sync ─────────────────────────────────────

async def test_slack_sync_returns_counts(client, monkeypatch):
    async def _fake_sync(db, org_id):
        return {"channels_synced": 3, "messages_read": 45, "error": None}

    async def _status(db, org_id):
        return _CONNECTED

    monkeypatch.setattr(slack_service, "sync_slack_messages", _fake_sync)
    monkeypatch.setattr(slack_service, "get_slack_status", _status)

    response = await client.post("/api/v1/integrations/slack/sync", headers=_ceo_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["channels_synced"] == 3
    assert body["messages_read"] == 45


async def test_slack_sync_not_connected_returns_400(client, monkeypatch):
    async def _fake_sync_fail(db, org_id):
        return {"channels_synced": 0, "messages_read": 0, "error": "Slack integration is not connected"}

    monkeypatch.setattr(slack_service, "sync_slack_messages", _fake_sync_fail)

    response = await client.post("/api/v1/integrations/slack/sync", headers=_ceo_headers())
    assert response.status_code == 400


# ── POST /api/v1/integrations/slack/send ─────────────────────────────────────

async def test_slack_send_success(client, monkeypatch):
    async def _fake_send(db, org_id, channel_id, text):
        return {"ok": True, "ts": "1234567890.000100"}

    monkeypatch.setattr(slack_service, "send_to_slack", _fake_send)

    response = await client.post(
        "/api/v1/integrations/slack/send",
        json={"channel_id": "C01234", "text": "Hello team!"},
        headers=_ceo_headers(),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_slack_send_not_connected_returns_400(client, monkeypatch):
    async def _fake_send_fail(db, org_id, channel_id, text):
        raise ValueError("Slack integration is not connected")

    monkeypatch.setattr(slack_service, "send_to_slack", _fake_send_fail)

    response = await client.post(
        "/api/v1/integrations/slack/send",
        json={"channel_id": "C01234", "text": "Hello!"},
        headers=_ceo_headers(),
    )
    assert response.status_code == 400


async def test_slack_send_denied_for_manager(client):
    mgr = create_access_token({"id": 3, "email": "manager@org1.com", "role": "MANAGER", "org_id": 1, "token_version": 1})
    response = await client.post(
        "/api/v1/integrations/slack/send",
        json={"channel_id": "C01234", "text": "Hello!"},
        headers={"Authorization": f"Bearer {mgr}"},
    )
    assert response.status_code == 403


async def test_slack_sync_malformed_result_returns_502(client, monkeypatch):
    async def _bad_shape(db, org_id):
        return {"channels_synced": 3, "messages_read": "45", "error": None}

    monkeypatch.setattr(slack_service, "sync_slack_messages", _bad_shape)
    response = await client.post("/api/v1/integrations/slack/sync", headers=_ceo_headers())
    assert response.status_code == 502
