"""
Tests for TOTP MFA — service layer, API endpoints, and login enforcement.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.models.organization import Organization
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ceo_token() -> str:
    from app.core.security import create_access_token
    return create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1, "token_version": 1},
        expires_minutes=60,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        s.add(Organization(id=1, name="Test Org", slug="test-org"))
        s.add(User(
            id=1, organization_id=1, name="CEO", email="ceo@org1.com",
            password_hash="unused", role="CEO", is_active=True, token_version=1,
        ))
        await s.commit()

    from app.core.deps import get_db

    async def _override():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Service-layer unit tests (no DB, no HTTP)
# ---------------------------------------------------------------------------

def test_generate_secret_is_base32():
    pytest.importorskip("pyotp")
    import re

    from app.services.mfa import generate_secret
    secret = generate_secret()
    assert len(secret) >= 16
    assert re.match(r"^[A-Z2-7]+=*$", secret), "Secret must be valid base32"


def test_verify_code_valid():
    pytest.importorskip("pyotp")
    import pyotp

    from app.services.mfa import generate_secret, verify_code
    secret = generate_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_code(secret, code) is True


def test_verify_code_wrong():
    pytest.importorskip("pyotp")
    from app.services.mfa import generate_secret, verify_code
    secret = generate_secret()
    assert verify_code(secret, "000000") is False


def test_verify_code_empty_inputs():
    from app.services.mfa import verify_code
    assert verify_code("", "123456") is False
    assert verify_code("JBSWY3DPEHPK3PXP", "") is False


def test_verify_code_non_digits():
    from app.services.mfa import verify_code
    assert verify_code("JBSWY3DPEHPK3PXP", "abcdef") is False


def test_provisioning_uri_format():
    pytest.importorskip("pyotp")
    from app.services.mfa import generate_secret, get_provisioning_uri
    secret = generate_secret()
    uri = get_provisioning_uri(secret, "test@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "test%40example.com" in uri or "test@example.com" in uri


def test_get_qr_data_uri_returns_none_or_png():
    pytest.importorskip("pyotp")
    from app.services.mfa import generate_secret, get_qr_data_uri
    secret = generate_secret()
    result = get_qr_data_uri(secret, "test@example.com")
    if result is not None:
        assert result.startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mfa_status_not_enabled(client):
    r = await client.get(
        "/api/v1/mfa/status",
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )
    assert r.status_code == 200
    assert r.json()["mfa_enabled"] is False


@pytest.mark.asyncio
async def test_mfa_setup_returns_secret(client):
    pytest.importorskip("pyotp")
    r = await client.post(
        "/api/v1/mfa/setup",
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "secret" in data
    assert "provisioning_uri" in data
    assert data["provisioning_uri"].startswith("otpauth://totp/")


@pytest.mark.asyncio
async def test_mfa_confirm_with_valid_code(client):
    pytest.importorskip("pyotp")
    import pyotp

    # Setup first
    r = await client.post(
        "/api/v1/mfa/setup",
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )
    secret = r.json()["secret"]

    # Confirm with valid code
    code = pyotp.TOTP(secret).now()
    r = await client.post(
        "/api/v1/mfa/confirm",
        json={"totp_code": code},
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # Status should now reflect enabled
    r = await client.get(
        "/api/v1/mfa/status",
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )
    assert r.json()["mfa_enabled"] is True


@pytest.mark.asyncio
async def test_mfa_confirm_with_wrong_code(client):
    pytest.importorskip("pyotp")
    import pyotp as _pyotp
    r2 = await client.post("/api/v1/mfa/setup", headers={"Authorization": f"Bearer {_ceo_token()}"})
    _secret = r2.json()["secret"]
    _totp = _pyotp.TOTP(_secret)
    wrong_code = "000000"
    for _c in ("000000", "111111", "222222", "333333"):
        if not _totp.verify(_c, valid_window=1):
            wrong_code = _c
            break
    r = await client.post(
        "/api/v1/mfa/confirm",
        json={"totp_code": wrong_code},
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_mfa_disable_requires_valid_code(client):
    pytest.importorskip("pyotp")
    import pyotp

    # Enable MFA first
    r = await client.post("/api/v1/mfa/setup", headers={"Authorization": f"Bearer {_ceo_token()}"})
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    await client.post(
        "/api/v1/mfa/confirm",
        json={"totp_code": code},
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )

    # Wrong code -> fail (pick a code guaranteed invalid within the +/-1 window)
    import pyotp as _pyotp
    _totp = _pyotp.TOTP(secret)
    wrong_code = "000000"
    for _candidate in ("000000", "111111", "222222", "333333"):
        if not _totp.verify(_candidate, valid_window=1):
            wrong_code = _candidate
            break
    r = await client.post(
        "/api/v1/mfa/disable",
        json={"totp_code": wrong_code},
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )
    assert r.status_code == 401

    # Correct code -> succeed
    code = pyotp.TOTP(secret).now()
    r = await client.post(
        "/api/v1/mfa/disable",
        json={"totp_code": code},
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_mfa_setup_conflict_when_already_enabled(client):
    pytest.importorskip("pyotp")
    import pyotp

    r = await client.post("/api/v1/mfa/setup", headers={"Authorization": f"Bearer {_ceo_token()}"})
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    await client.post(
        "/api/v1/mfa/confirm",
        json={"totp_code": code},
        headers={"Authorization": f"Bearer {_ceo_token()}"},
    )

    # Setup again while already enabled -> 409
    r = await client.post("/api/v1/mfa/setup", headers={"Authorization": f"Bearer {_ceo_token()}"})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Login enforcement tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mfa_enabled_client():
    """Client fixture where the CEO user has a real password + MFA enabled."""
    pytest.importorskip("pyotp")
    from app.core.security import hash_password

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    from app.services.mfa import generate_secret
    secret = generate_secret()
    pw_hash = hash_password("TestPass2026!")

    async with Session() as s:
        s.add(Organization(id=1, name="Test Org", slug="test-org"))
        s.add(User(
            id=1, organization_id=1, name="CEO", email="ceo@org1.com",
            password_hash=pw_hash, role="CEO", is_active=True, token_version=1,
            totp_secret=secret, mfa_enabled=True,
        ))
        await s.commit()

    from app.core.deps import get_db

    async def _override():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, secret
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_login_mfa_required_when_no_code(mfa_enabled_client):
    """Login with correct password but no TOTP code -> 401 + X-MFA-Required header."""
    client, _ = mfa_enabled_client
    r = await client.post(
        "/web/login",
        data={"username": "ceo@org1.com", "password": "TestPass2026!"},
    )
    assert r.status_code == 401
    assert (
        r.headers.get("x-mfa-required") == "true"
        or "mfa" in r.json().get("detail", "").lower()
    )


@pytest.mark.asyncio
async def test_login_mfa_wrong_code_rejected(mfa_enabled_client):
    """Login with correct password + wrong TOTP code -> 401."""
    import pyotp as _pyotp
    client, secret = mfa_enabled_client
    _totp = _pyotp.TOTP(secret)
    wrong_code = "000000"
    for _c in ("000000", "111111", "222222", "333333"):
        if not _totp.verify(_c, valid_window=1):
            wrong_code = _c
            break
    r = await client.post(
        "/web/login",
        data={"username": "ceo@org1.com", "password": "TestPass2026!", "totp_code": wrong_code},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_mfa_correct_code_succeeds(mfa_enabled_client):
    """Login with correct password + correct TOTP code -> success (200 + cookies)."""
    import pyotp
    client, secret = mfa_enabled_client
    code = pyotp.TOTP(secret).now()
    r = await client.post(
        "/web/login",
        data={"username": "ceo@org1.com", "password": "TestPass2026!", "totp_code": code},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "pc_session" in r.cookies


@pytest.mark.asyncio
async def test_api_login_mfa_required_when_no_code(mfa_enabled_client):
    """API login with correct password but no TOTP code -> 401 + MFA-required signal."""
    client, _ = mfa_enabled_client
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "ceo@org1.com", "password": "TestPass2026!"},
    )
    assert r.status_code == 401
    assert (
        r.headers.get("x-mfa-required") == "true"
        or "mfa" in r.json().get("detail", "").lower()
    )


@pytest.mark.asyncio
async def test_api_login_mfa_wrong_code_rejected(mfa_enabled_client):
    """API login with correct password + wrong TOTP code -> 401."""
    import pyotp as _pyotp

    client, secret = mfa_enabled_client
    _totp = _pyotp.TOTP(secret)
    wrong_code = "000000"
    for _c in ("000000", "111111", "222222", "333333"):
        if not _totp.verify(_c, valid_window=1):
            wrong_code = _c
            break
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "ceo@org1.com", "password": "TestPass2026!", "totp_code": wrong_code},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_api_login_mfa_correct_code_succeeds(mfa_enabled_client):
    """API login with correct password + valid TOTP code returns bearer token."""
    import pyotp

    client, secret = mfa_enabled_client
    code = pyotp.TOTP(secret).now()
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "ceo@org1.com", "password": "TestPass2026!", "totp_code": code},
    )
    assert r.status_code == 200
    token = r.json().get("access_token")
    assert token

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


@pytest_asyncio.fixture
async def mfa_required_unenrolled_client():
    """Client fixture where MFA policy is enabled but user is not yet enrolled."""
    from app.core.security import hash_password

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    pw_hash = hash_password("TestPass2026!")
    async with Session() as s:
        s.add(Organization(id=1, name="Test Org", slug="test-org"))
        s.add(
            User(
                id=1,
                organization_id=1,
                name="CEO",
                email="ceo@org1.com",
                password_hash=pw_hash,
                role="CEO",
                is_active=True,
                token_version=1,
                mfa_enabled=False,
            )
        )
        await s.commit()

    from app.core.deps import get_db

    async def _override():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_mfa_required_policy_issues_bootstrap_token(mfa_required_unenrolled_client):
    pytest.importorskip("pyotp")
    client = mfa_required_unenrolled_client
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "ceo@org1.com", "password": "TestPass2026!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Bootstrap token must not access regular business endpoints.
    blocked = await client.get("/api/v1/tasks", headers=headers)
    assert blocked.status_code == 403
    assert "MFA enrollment required" in blocked.json().get("detail", "")

    # Bootstrap token is allowed to reach MFA setup endpoints.
    setup = await client.post("/api/v1/mfa/setup", headers=headers)
    assert setup.status_code == 200
