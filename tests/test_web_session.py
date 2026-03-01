from datetime import UTC, datetime

from app.core.deps import get_db
from app.core.security import hash_password
from app.logs import audit as audit_log
from app.main import app as fastapi_app
from app.models.organization import Organization
from app.models.user import User


def _cookie_header(cookies) -> dict:
    """Build a raw Cookie header dict from an httpx Cookies/response.cookies object.

    httpx ASGI transport does not auto-forward Set-Cookie values on subsequent
    requests because there is no real domain to match against.  Passing the
    cookies as a raw ``Cookie`` header bypasses the jar entirely and ensures the
    ASGI app receives them.
    """
    value = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return {"Cookie": value}


async def _seed_web_user() -> None:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        org = Organization(name="Web Org", slug="web-org")
        session.add(org)
        await session.flush()

        user = User(
            organization_id=org.id,
            name="Web CEO",
            email="web.ceo@example.com",
            password_hash=hash_password("secret123"),
            role="CEO",
            is_active=True,
            created_at=datetime.now(UTC),
        )
        session.add(user)
        await session.commit()
    finally:
        await agen.aclose()


async def test_web_login_sets_session_and_session_endpoint(client):
    await _seed_web_user()
    login = await client.post(
        "/web/login",
        data={"username": "web.ceo@example.com", "password": "secret123"},
    )
    assert login.status_code == 200
    assert "pc_session" in login.cookies
    assert "pc_csrf" in login.cookies

    session_info = await client.get("/web/session", headers=_cookie_header(login.cookies))
    assert session_info.status_code == 200
    assert session_info.json()["logged_in"] is True


async def test_web_login_page_uses_static_assets(client):
    page = await client.get("/web/login")
    assert page.status_code == 200
    assert "/static/css/login.css" in page.text
    assert "/static/js/login-page.js" in page.text


async def test_web_daily_run_requires_csrf(client):
    await _seed_web_user()
    login = await client.post(
        "/web/login",
        data={"username": "web.ceo@example.com", "password": "secret123"},
    )
    assert login.status_code == 200

    blocked = await client.post("/web/ops/daily-run?draft_email_limit=0")
    assert blocked.status_code == 403


async def test_web_daily_run_with_csrf_succeeds(client):
    await _seed_web_user()
    login = await client.post(
        "/web/login",
        data={"username": "web.ceo@example.com", "password": "secret123"},
    )
    assert login.status_code == 200
    csrf = login.cookies.get("pc_csrf")
    assert csrf

    run = await client.post(
        "/web/ops/daily-run?draft_email_limit=0",
        headers={**_cookie_header(login.cookies), "X-CSRF-Token": csrf},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["requires_approval"] is True


async def test_web_logout_invalidates_only_current_user_session(client):
    user1 = await client.post(
        "/api/v1/users",
        json={
            "organization_id": 1,
            "name": "Logout User 1",
            "email": "logout-u1@example.com",
            "password": "StrongPass123!",
            "role": "STAFF",
        },
    )
    assert user1.status_code == 201
    user2 = await client.post(
        "/api/v1/users",
        json={
            "organization_id": 1,
            "name": "Logout User 2",
            "email": "logout-u2@example.com",
            "password": "StrongPass123!",
            "role": "STAFF",
        },
    )
    assert user2.status_code == 201

    token1 = (await client.post(
        "/token",
        data={"username": "logout-u1@example.com", "password": "StrongPass123!"},
    )).json()["access_token"]
    token2 = (await client.post(
        "/token",
        data={"username": "logout-u2@example.com", "password": "StrongPass123!"},
    )).json()["access_token"]

    login = await client.post(
        "/web/login",
        data={"username": "logout-u1@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200
    csrf = login.cookies.get("pc_csrf")
    assert csrf

    logout = await client.post(
        "/web/logout",
        headers={**_cookie_header(login.cookies), "X-CSRF-Token": csrf},
    )
    assert logout.status_code == 200

    me1 = await client.get("/me", headers={"Authorization": f"Bearer {token1}"})
    me2 = await client.get("/me", headers={"Authorization": f"Bearer {token2}"})
    assert me1.status_code == 401
    assert me2.status_code == 200


async def test_web_login_failure_audit_redacts_raw_username(client, monkeypatch):
    await _seed_web_user()
    captured: dict = {}

    async def fake_record_action(*_args, **kwargs):
        captured["payload_json"] = kwargs.get("payload_json") or {}
        return None

    monkeypatch.setattr(audit_log, "record_action", fake_record_action)

    resp = await client.post(
        "/web/login",
        data={"username": "web.ceo@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    payload = captured.get("payload_json", {})
    assert "username" not in payload
    assert payload.get("username_fingerprint")
