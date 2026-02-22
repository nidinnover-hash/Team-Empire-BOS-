from datetime import datetime, timezone

from app.core.deps import get_db
from app.core.security import hash_password
from app.main import app as fastapi_app
from app.models.organization import Organization
from app.models.user import User


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
            created_at=datetime.now(timezone.utc),
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

    session_info = await client.get("/web/session")
    assert session_info.status_code == 200
    assert session_info.json()["logged_in"] is True


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
        headers={"X-CSRF-Token": csrf},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["requires_approval"] is True
