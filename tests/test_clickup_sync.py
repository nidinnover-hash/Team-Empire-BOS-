"""
Tests for ClickUp integration endpoints.

All ClickUp API calls are mocked via monkeypatch so no real token is needed.
"""
from app.core.security import create_access_token
from app.services import clickup_service


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 1, "email": "ceo@org.com", "role": "CEO", "org_id": org_id})
    return {"Authorization": f"Bearer {token}"}


_DISCONNECTED_STATUS = {"connected": False, "last_sync_at": None, "username": None, "team_id": None}
_CONNECTED_STATUS = {"connected": True, "last_sync_at": "2026-02-23T08:00:00Z", "username": "nidin", "team_id": "team_123"}


# ── POST /api/v1/integrations/clickup/connect ────────────────────────────────

async def test_clickup_connect_success(client, monkeypatch):
    async def _fake_connect(db, org_id, api_token):
        return {"id": 1, "status": "connected", "username": "nidin", "team_id": "team_123"}

    monkeypatch.setattr(clickup_service, "connect_clickup", _fake_connect)

    response = await client.post(
        "/api/v1/integrations/clickup/connect",
        json={"api_token": "pk_XXXX_YYYY"},
        headers=_ceo_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["connected"] is True
    assert body["username"] == "nidin"
    assert body["team_id"] == "team_123"


async def test_clickup_connect_bad_token_returns_400(client, monkeypatch):
    async def _fake_connect_fail(db, org_id, api_token):
        raise ValueError("Invalid token")

    monkeypatch.setattr(clickup_service, "connect_clickup", _fake_connect_fail)

    response = await client.post(
        "/api/v1/integrations/clickup/connect",
        json={"api_token": "bad_token"},
        headers=_ceo_headers(),
    )
    assert response.status_code == 400


async def test_clickup_connect_denied_for_staff(client):
    staff_token = create_access_token({"id": 2, "email": "staff@org.com", "role": "STAFF", "org_id": 1})
    response = await client.post(
        "/api/v1/integrations/clickup/connect",
        json={"api_token": "pk_anything"},
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert response.status_code == 403


async def test_clickup_connect_missing_token_returns_422(client):
    response = await client.post(
        "/api/v1/integrations/clickup/connect",
        json={},
        headers=_ceo_headers(),
    )
    assert response.status_code == 422


# ── GET /api/v1/integrations/clickup/status ──────────────────────────────────

async def test_clickup_status_not_connected(client, monkeypatch):
    async def _status(db, org_id):
        return _DISCONNECTED_STATUS

    monkeypatch.setattr(clickup_service, "get_clickup_status", _status)

    response = await client.get("/api/v1/integrations/clickup/status", headers=_ceo_headers())
    assert response.status_code == 200
    assert response.json()["connected"] is False


async def test_clickup_status_connected(client, monkeypatch):
    async def _status(db, org_id):
        return _CONNECTED_STATUS

    monkeypatch.setattr(clickup_service, "get_clickup_status", _status)

    response = await client.get("/api/v1/integrations/clickup/status", headers=_ceo_headers())
    body = response.json()
    assert body["connected"] is True
    assert body["username"] == "nidin"


# ── POST /api/v1/integrations/clickup/sync ───────────────────────────────────

async def test_clickup_sync_returns_synced_count(client, monkeypatch):
    async def _fake_sync(db, org_id):
        return {"synced": 12, "error": None}

    async def _status(db, org_id):
        return _CONNECTED_STATUS

    monkeypatch.setattr(clickup_service, "sync_clickup_tasks", _fake_sync)
    monkeypatch.setattr(clickup_service, "get_clickup_status", _status)

    response = await client.post("/api/v1/integrations/clickup/sync", headers=_ceo_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["synced"] == 12


async def test_clickup_sync_when_not_connected_returns_400(client, monkeypatch):
    async def _fake_sync_fail(db, org_id):
        return {"synced": 0, "error": "No ClickUp integration configured for this organization"}

    monkeypatch.setattr(clickup_service, "sync_clickup_tasks", _fake_sync_fail)

    response = await client.post("/api/v1/integrations/clickup/sync", headers=_ceo_headers())
    assert response.status_code == 400


async def test_clickup_sync_denied_for_manager(client):
    mgr_token = create_access_token({"id": 3, "email": "mgr@org.com", "role": "MANAGER", "org_id": 1})
    response = await client.post(
        "/api/v1/integrations/clickup/sync",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert response.status_code == 403
