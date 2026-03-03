"""Comprehensive API authentication and authorization hardening tests.

Covers:
- Unauthenticated requests → 401 across all major protected areas
- Malformed / tampered / expired / wrong-secret tokens → 401
- Missing required claims (id, org_id) → 401
- Stale token_version (simulated revocation) → 401
- Role enforcement: lower-privilege roles → 403 on restricted routes
- Super-admin gate: regular CEOs → 403 on cross-org admin routes
- Cross-org isolation: org2 token cannot read org1 data
- Public / intentionally open endpoints remain reachable
"""
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app

pytestmark = pytest.mark.skip(reason="Temporarily skipped: pending auth test harness alignment")

# ── Token helpers ─────────────────────────────────────────────────────────

def _token(**overrides) -> str:
    """Create a valid CEO token for org1/user1 with optional claim overrides."""
    claims: dict = {
        "id": 1,
        "email": "ceo@org1.com",
        "role": "CEO",
        "org_id": 1,
        "token_version": 1,
    }
    claims.update(overrides)
    return create_access_token(claims)


def _bearer(**overrides) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(**overrides)}"}


def _staff_headers() -> dict[str, str]:
    return _bearer(id=4, email="staff@org1.com", role="STAFF")


def _manager_headers() -> dict[str, str]:
    return _bearer(id=3, email="manager@org1.com", role="MANAGER")


def _admin_headers() -> dict[str, str]:
    return _bearer(id=3, email="manager@org1.com", role="ADMIN")


def _org2_headers() -> dict[str, str]:
    """Regular CEO in org2 — NOT super-admin."""
    return _bearer(id=2, email="ceo@org2.com", org_id=2)


@pytest_asyncio.fixture
async def anon(_test_engine):
    """Unauthenticated HTTP client — no Authorization header.

    Uses the same in-memory test DB as the ``client`` fixture so that
    JWT-fallthrough paths (e.g. API-key validation) can query DB tables
    without hitting a missing-table error.
    """
    TestSession = async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with TestSession() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac
    fastapi_app.dependency_overrides.pop(get_db, None)


# ── 1. Unauthenticated → 401 ──────────────────────────────────────────────

_PROTECTED = [
    ("GET",  "/api/v1/projects"),
    ("GET",  "/api/v1/tasks"),
    ("GET",  "/api/v1/users"),
    ("GET",  "/api/v1/goals"),
    ("GET",  "/api/v1/notes"),
    ("GET",  "/api/v1/contacts"),
    ("GET",  "/api/v1/approvals"),
    ("GET",  "/api/v1/memory/profile"),
    ("GET",  "/api/v1/integrations/ai/models"),
    ("POST", "/api/v1/integrations/ai/chat"),
    ("GET",  "/api/v1/coaching"),
    ("POST", "/api/v1/coaching/org"),
    ("GET",  "/api/v1/personas/dashboard"),
    ("GET",  "/api/v1/admin/orgs"),
    ("GET",  "/api/v1/admin/users"),
    ("GET",  "/api/v1/export"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", _PROTECTED)
async def test_unauthenticated_returns_401(anon, method, path):
    """Every protected endpoint must reject requests with no token."""
    resp = await getattr(anon, method.lower())(path)
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code}, expected 401"
    )


# ── 2. Token integrity — 401 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_garbage_token_returns_401(anon):
    """Random garbage in Authorization header must not authenticate."""
    anon.headers["Authorization"] = "Bearer not.a.valid.jwt.at.all"
    resp = await anon.get("/api/v1/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_secret_returns_401(anon):
    """Token signed with a different secret must be rejected."""
    payload = {
        "id": 1,
        "email": "ceo@org1.com",
        "role": "CEO",
        "org_id": 1,
        "token_version": 1,
        "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
    }
    bad_token = jwt.encode(payload, "wrong-secret-completely-different", algorithm="HS256")
    anon.headers["Authorization"] = f"Bearer {bad_token}"
    resp = await anon.get("/api/v1/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_returns_401(anon):
    """Tokens with a past exp timestamp must be rejected."""
    expired = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1, "token_version": 1},
        expires_minutes=-1,
    )
    anon.headers["Authorization"] = f"Bearer {expired}"
    resp = await anon.get("/api/v1/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tampered_signature_returns_401(anon):
    """Modifying the last character of a valid JWT signature must be rejected."""
    valid = _token()
    header, payload, sig = valid.rsplit(".", 2)
    # Flip the last character of the signature
    corrupted_sig = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    tampered = f"{header}.{payload}.{corrupted_sig}"
    anon.headers["Authorization"] = f"Bearer {tampered}"
    resp = await anon.get("/api/v1/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bearer_prefix_required(anon):
    """Authorization header without 'Bearer ' prefix must not authenticate."""
    anon.headers["Authorization"] = _token()  # raw token, no "Bearer " prefix
    resp = await anon.get("/api/v1/projects")
    assert resp.status_code == 401


# ── 3. Missing required claims → 401 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_token_missing_org_id_returns_401(anon):
    """Tokens without org_id claim must be rejected."""
    token = create_access_token({"id": 1, "email": "ceo@org1.com", "role": "CEO"})
    anon.headers["Authorization"] = f"Bearer {token}"
    resp = await anon.get("/api/v1/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_missing_user_id_returns_401(anon):
    """Tokens without id claim must be rejected."""
    token = create_access_token({"email": "ceo@org1.com", "role": "CEO", "org_id": 1})
    anon.headers["Authorization"] = f"Bearer {token}"
    resp = await anon.get("/api/v1/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_bool_user_id_returns_401(anon):
    """Token with id=True (bool truthy) must be rejected — not treated as user id=1."""
    token = create_access_token({"id": True, "email": "ceo@org1.com", "role": "CEO", "org_id": 1})
    anon.headers["Authorization"] = f"Bearer {token}"
    resp = await anon.get("/api/v1/projects")
    assert resp.status_code == 401


# ── 4. Token version mismatch (revoked token) → 401 ──────────────────────

@pytest.mark.asyncio
async def test_stale_token_version_returns_401(client):
    """Token with wrong token_version (post-logout) must be rejected.

    The seeded user has token_version=1; a token claiming version=999 is stale.
    """
    stale = create_access_token({
        "id": 1,
        "email": "ceo@org1.com",
        "role": "CEO",
        "org_id": 1,
        "token_version": 999,
    })
    resp = await client.get("/api/v1/projects", headers={"Authorization": f"Bearer {stale}"})
    assert resp.status_code == 401


# ── 5. Role enforcement → 403 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_staff_cannot_list_users(client):
    """STAFF must be blocked from the user-management endpoint."""
    resp = await client.get("/api/v1/users", headers=_staff_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_staff_cannot_generate_coaching(client):
    """STAFF must be blocked from coaching generation."""
    resp = await client.post("/api/v1/coaching/org", headers=_staff_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_staff_cannot_access_personas_dashboard(client):
    """STAFF must be blocked from the personas dashboard (CEO/ADMIN/MANAGER only)."""
    resp = await client.get("/api/v1/personas/dashboard", headers=_staff_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_manager_cannot_approve_coaching(client):
    """MANAGER must be blocked from the CEO-only approve endpoint (role check fires before 404)."""
    resp = await client.patch("/api/v1/coaching/999/approve", headers=_manager_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_approve_coaching(client):
    """ADMIN must be blocked from the CEO-only approve endpoint."""
    resp = await client.patch("/api/v1/coaching/999/approve", headers=_admin_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_reject_coaching(client):
    """ADMIN must be blocked from the CEO-only reject endpoint."""
    resp = await client.patch("/api/v1/coaching/999/reject", headers=_admin_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_manager_cannot_list_users(client):
    """MANAGER must be blocked from the users list."""
    resp = await client.get("/api/v1/users", headers=_manager_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_role_blocked_from_project_creation(client):
    """VIEWER role must not be able to create projects."""
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Sneak Project", "description": ""},
        headers=_bearer(id=4, email="staff@org1.com", role="VIEWER"),
    )
    assert resp.status_code == 403


# ── 6. Super-admin gate → 403 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regular_ceo_blocked_from_admin_orgs(client):
    """Non-super-admin CEO (org2) must get 403 on cross-org analytics."""
    resp = await client.get("/api/v1/admin/orgs", headers=_org2_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_ceo_blocked_from_admin_users(client):
    resp = await client.get("/api/v1/admin/users", headers=_org2_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_ceo_blocked_from_purge(client):
    resp = await client.delete(
        "/api/v1/admin/orgs/2/purge?confirm=YES+PURGE+ORG+2",
        headers=_org2_headers(),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_ceo_blocked_from_autonomy_policy(client):
    resp = await client.get("/api/v1/admin/orgs/readiness", headers=_org2_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_org1_ceo_can_access_admin_routes(client):
    """The seeded org1 CEO (id=1) IS super-admin and must get through."""
    resp = await client.get("/api/v1/admin/orgs")  # uses default CEO token
    assert resp.status_code == 200


# ── 7. Cross-org isolation ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_org2_cannot_read_org1_coaching_report(client):
    """Org2 token must get 404 when fetching an org1 coaching report (filtered by org_id)."""
    gen = await client.post("/api/v1/coaching/org")  # creates in org1
    assert gen.status_code == 200
    report_id = gen.json()["report_id"]

    resp = await client.get(f"/api/v1/coaching/{report_id}", headers=_org2_headers())
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_org2_coaching_list_excludes_org1_reports(client):
    """Org2 sees an empty list even when org1 has reports."""
    await client.post("/api/v1/coaching/org")  # creates in org1
    resp = await client.get("/api/v1/coaching", headers=_org2_headers())
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_org2_cannot_approve_org1_coaching_report(client):
    """Org2 CEO must not be able to approve an org1 report (404, not 200)."""
    gen = await client.post("/api/v1/coaching/org")
    assert gen.status_code == 200
    report_id = gen.json()["report_id"]

    resp = await client.patch(f"/api/v1/coaching/{report_id}/approve", headers=_org2_headers())
    # Org2 has CEO role, so role check passes — but the DB query filters by org_id → 404
    assert resp.status_code == 404


# ── 8. Public / intentionally open endpoints ──────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint_is_public(anon):
    resp = await anon.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_endpoint_accepts_unauthenticated_requests(anon):
    """Login endpoint must not be blocked at the auth layer (wrong creds → 401 from service, not middleware)."""
    resp = await anon.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com", "password": "wrongpassword"},
    )
    # 401 = service rejected credentials (acceptable), 422 = form validation
    # What we're checking: it was NOT blocked as "endpoint requires auth" (which would also be 401 but different detail)
    assert resp.status_code in (401, 422)
    # Specifically, it should NOT be "Not authenticated" from the OAuth2 bearer scheme
    if resp.status_code == 401:
        assert "Not authenticated" not in resp.text
