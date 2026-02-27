"""
Tests for GitHub integration endpoints.

All GitHub API calls are mocked so no real PAT is required.
"""
from app.core.security import create_access_token
from app.services import github_service


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


_DISCONNECTED = {"connected": False, "last_sync_at": None, "login": None, "repos_tracked": None}
_CONNECTED = {"connected": True, "last_sync_at": "2026-02-23T09:00:00Z", "login": "nidinv", "repos_tracked": 8}


# ── POST /api/v1/integrations/github/connect ─────────────────────────────────

async def test_github_connect_success(client, monkeypatch):
    async def _fake_connect(db, org_id, api_token):
        return {"id": 1, "status": "connected", "login": "nidinv"}

    monkeypatch.setattr(github_service, "connect_github", _fake_connect)

    response = await client.post(
        "/api/v1/integrations/github/connect",
        json={"api_token": "ghp_XXXXXXXXXXXX"},
        headers=_ceo_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["connected"] is True
    assert body["login"] == "nidinv"


async def test_github_connect_bad_token_returns_400(client, monkeypatch):
    async def _fake_connect_fail(db, org_id, api_token):
        raise ValueError("Bad credentials")

    monkeypatch.setattr(github_service, "connect_github", _fake_connect_fail)

    response = await client.post(
        "/api/v1/integrations/github/connect",
        json={"api_token": "bad"},
        headers=_ceo_headers(),
    )
    assert response.status_code == 400


async def test_github_connect_error_does_not_echo_token(client, monkeypatch):
    sensitive_token = "ghp_SUPER_SECRET_TOKEN_1234567890"

    async def _fake_connect_fail(db, org_id, api_token):
        raise RuntimeError(f"auth failed for token={api_token}")

    monkeypatch.setattr(github_service, "connect_github", _fake_connect_fail)

    response = await client.post(
        "/api/v1/integrations/github/connect",
        json={"api_token": sensitive_token},
        headers=_ceo_headers(),
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert sensitive_token not in detail


async def test_github_connect_denied_for_staff(client):
    staff = create_access_token({"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": 1, "token_version": 1})
    response = await client.post(
        "/api/v1/integrations/github/connect",
        json={"api_token": "ghp_anything"},
        headers={"Authorization": f"Bearer {staff}"},
    )
    assert response.status_code == 403


async def test_github_connect_missing_token_returns_422(client):
    response = await client.post(
        "/api/v1/integrations/github/connect",
        json={},
        headers=_ceo_headers(),
    )
    assert response.status_code == 422


# ── GET /api/v1/integrations/github/status ───────────────────────────────────

async def test_github_status_not_connected(client, monkeypatch):
    async def _status(db, org_id):
        return _DISCONNECTED

    monkeypatch.setattr(github_service, "get_github_status", _status)

    response = await client.get("/api/v1/integrations/github/status", headers=_ceo_headers())
    assert response.status_code == 200
    assert response.json()["connected"] is False


async def test_github_status_connected(client, monkeypatch):
    async def _status(db, org_id):
        return _CONNECTED

    monkeypatch.setattr(github_service, "get_github_status", _status)

    response = await client.get("/api/v1/integrations/github/status", headers=_ceo_headers())
    body = response.json()
    assert body["connected"] is True
    assert body["login"] == "nidinv"
    assert body["repos_tracked"] == 8


# ── POST /api/v1/integrations/github/sync ────────────────────────────────────

async def test_github_sync_returns_counts(client, monkeypatch):
    async def _fake_sync(db, org_id):
        return {"prs_synced": 7, "issues_synced": 3, "error": None}

    async def _status(db, org_id):
        return _CONNECTED

    monkeypatch.setattr(github_service, "sync_github", _fake_sync)
    monkeypatch.setattr(github_service, "get_github_status", _status)

    response = await client.post("/api/v1/integrations/github/sync", headers=_ceo_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["prs_synced"] == 7
    assert body["issues_synced"] == 3


async def test_github_sync_not_connected_returns_400(client, monkeypatch):
    async def _fake_sync_fail(db, org_id):
        return {"prs_synced": 0, "issues_synced": 0, "error": "GitHub integration is not connected"}

    monkeypatch.setattr(github_service, "sync_github", _fake_sync_fail)

    response = await client.post("/api/v1/integrations/github/sync", headers=_ceo_headers())
    assert response.status_code == 400


async def test_github_sync_denied_for_manager(client):
    mgr = create_access_token({"id": 3, "email": "manager@org1.com", "role": "MANAGER", "org_id": 1, "token_version": 1})
    response = await client.post(
        "/api/v1/integrations/github/sync",
        headers={"Authorization": f"Bearer {mgr}"},
    )
    assert response.status_code == 403


async def test_github_sync_malformed_result_returns_502(client, monkeypatch):
    async def _bad_shape(db, org_id):
        return {"prs_synced": "7", "issues_synced": 3, "error": None}

    monkeypatch.setattr(github_service, "sync_github", _bad_shape)
    response = await client.post("/api/v1/integrations/github/sync", headers=_ceo_headers())
    assert response.status_code == 502


async def test_github_sync_timeout_returns_502(client, monkeypatch):
    async def _timeout(db, org_id):
        raise TimeoutError("github timeout")

    monkeypatch.setattr(github_service, "sync_github", _timeout)
    response = await client.post("/api/v1/integrations/github/sync", headers=_ceo_headers())
    assert response.status_code == 502
