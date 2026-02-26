import time

from app.core.config import settings
from app.core.security import decode_access_token


async def test_password_login_blocked_when_sso_required_on_token_endpoint(client, monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNT_SSO_REQUIRED", True)
    r = await client.post("/token", data={"username": "bad@example.com", "password": "wrongpass1"})
    assert r.status_code == 403
    assert "SSO is required" in r.json()["detail"]


async def test_password_login_blocked_when_sso_required_on_auth_router(client, monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNT_SSO_REQUIRED", True)
    r = await client.post("/api/v1/auth/login", data={"username": "bad@example.com", "password": "wrongpass1"})
    assert r.status_code == 403
    assert "SSO is required" in r.json()["detail"]


async def test_token_expiry_is_capped_by_account_session_hours(client, monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNT_SSO_REQUIRED", False)
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 480)
    monkeypatch.setattr(settings, "ACCOUNT_SESSION_MAX_HOURS", 1)

    created = await client.post(
        "/api/v1/users",
        json={
            "organization_id": 1,
            "name": "Session Cap User",
            "email": "session-cap@example.com",
            "password": "StrongPass123!",
            "role": "STAFF",
        },
    )
    assert created.status_code == 201

    login = await client.post(
        "/token",
        data={"username": "session-cap@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200
    payload = decode_access_token(login.json()["access_token"])
    ttl_seconds = int(payload["exp"]) - int(time.time())
    assert ttl_seconds <= 3600 + 5
    assert ttl_seconds >= 3500


async def test_web_login_cookie_max_age_is_capped_by_account_session_hours(client, monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNT_SSO_REQUIRED", False)
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 480)
    monkeypatch.setattr(settings, "ACCOUNT_SESSION_MAX_HOURS", 1)

    created = await client.post(
        "/api/v1/users",
        json={
            "organization_id": 1,
            "name": "Web Session Cap User",
            "email": "web-session-cap@example.com",
            "password": "StrongPass123!",
            "role": "STAFF",
        },
    )
    assert created.status_code == 201

    login = await client.post(
        "/web/login",
        data={"username": "web-session-cap@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200
    set_cookie_headers = login.headers.get_list("set-cookie")
    pc_session = next(
        h for h in set_cookie_headers
        if h.startswith("pc_session=") and "Max-Age=3600" in h
    )
    assert "Max-Age=3600" in pc_session
