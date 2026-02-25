"""Tests for hardening round 3: nonce replay, snapshot retention, middleware, password hashing."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.deps import get_db
from app.core.security import hash_password, verify_password
from app.main import app as fastapi_app


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_test_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


# ── 1. Google Calendar OAuth GET nonce replay ────────────────────────────────

async def test_gcal_oauth_get_callback_rejects_replay(client, monkeypatch):
    """Second call to Google Calendar OAuth GET callback with same state returns 400 (replay)."""
    from app.core import oauth_nonce

    # Clear nonce cache to avoid cross-test pollution
    oauth_nonce._used_nonces.clear()

    from app.core.oauth_state import sign_oauth_state

    state = str(sign_oauth_state(org_id=1))

    async def fake_exchange(*a, **kw):
        return {"access_token": "test", "refresh_token": "rt", "token_type": "Bearer"}

    monkeypatch.setattr("app.api.v1.endpoints.integrations.exchange_code_for_tokens", fake_exchange)
    monkeypatch.setattr("app.api.v1.endpoints.integrations.settings.GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setattr("app.api.v1.endpoints.integrations.settings.GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr("app.api.v1.endpoints.integrations.settings.GOOGLE_CALENDAR_REDIRECT_URI", "http://localhost/api/v1/integrations/google-calendar/oauth/callback")

    async def fake_connect(*a, **kw):
        class FakeIntegration:
            id = 1
            type = "google_calendar"
            status = "connected"
            config_json = {}
            last_sync_at = None
            last_sync_status = None
            organization_id = 1
            created_at = datetime.now(timezone.utc)
            updated_at = datetime.now(timezone.utc)
        return FakeIntegration()

    monkeypatch.setattr("app.api.v1.endpoints.integrations.integration_service.connect_integration", fake_connect)
    monkeypatch.setattr("app.api.v1.endpoints.integrations.integration_service.get_integration_by_type", AsyncMock(return_value=None))

    # First call should succeed
    r1 = await client.get(
        f"/api/v1/integrations/google-calendar/oauth/callback?code=test-code&state={state}",
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert r1.status_code in (200, 303), f"Expected success, got {r1.status_code}: {r1.text}"

    # Second call with same state is caught by verify_oauth_state nonce replay (400)
    r2 = await client.get(
        f"/api/v1/integrations/google-calendar/oauth/callback?code=test-code&state={state}",
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert r2.status_code == 400
    assert "Invalid OAuth state" in r2.text


# ── 2. OAuth nonce max-items cap ─────────────────────────────────────────────

def test_oauth_nonce_max_items_cap():
    """Nonce store does not grow unboundedly past _MAX_NONCE_ITEMS."""
    from app.core import oauth_nonce

    old_max = oauth_nonce._MAX_NONCE_ITEMS
    oauth_nonce._used_nonces.clear()
    try:
        oauth_nonce._MAX_NONCE_ITEMS = 10
        # Fill beyond the cap
        for i in range(15):
            oauth_nonce.consume_oauth_nonce_once(
                namespace="test_cap", nonce=f"nonce-{i}", max_age_seconds=3600
            )
        # Should be capped
        assert len(oauth_nonce._used_nonces) <= 11  # 10 cap + 1 new entry
    finally:
        oauth_nonce._MAX_NONCE_ITEMS = old_max
        oauth_nonce._used_nonces.clear()


# ── 3. X-Request-ID and X-Correlation-ID middleware ──────────────────────────

async def test_x_request_id_accepted_and_echoed(client):
    """Middleware accepts X-Request-ID and echoes both X-Request-ID and X-Correlation-ID."""
    custom_id = "test-req-id-12345"
    resp = await client.get("/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Correlation-ID") == custom_id
    assert resp.headers.get("X-Request-ID") == custom_id


async def test_x_correlation_id_takes_precedence(client):
    """X-Correlation-ID takes precedence over X-Request-ID when both are present."""
    resp = await client.get(
        "/health",
        headers={
            "X-Correlation-ID": "correlation-wins",
            "X-Request-ID": "request-loses",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Correlation-ID") == "correlation-wins"
    assert resp.headers.get("X-Request-ID") == "correlation-wins"


async def test_auto_generated_request_id_when_none_provided(client):
    """When no correlation or request ID provided, a UUID is generated."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    cid = resp.headers.get("X-Correlation-ID")
    rid = resp.headers.get("X-Request-ID")
    assert cid
    assert rid
    assert cid == rid
    # Should look like a UUID
    assert len(cid) == 36 and cid.count("-") == 4


# ── 4. Password hashing: PBKDF2 600k iterations ─────────────────────────────

def test_new_password_hash_uses_600k_iterations():
    """New password hashes use 600,000 iterations per OWASP recommendation."""
    hashed = hash_password("test-password-123")
    parts = hashed.split("$")
    assert parts[0] == "pbkdf2_sha256"
    assert int(parts[1]) == 600_000


def test_verify_password_still_works_with_old_100k_hash():
    """Existing 100k-iteration hashes still verify correctly (backward compat)."""
    import base64
    import hashlib
    import os

    salt = os.urandom(16)
    iterations = 100_000
    digest = hashlib.pbkdf2_hmac("sha256", "old-password".encode(), salt, iterations)
    old_hash = f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"

    assert verify_password("old-password", old_hash) is True
    assert verify_password("wrong-password", old_hash) is False


def test_new_hash_verifies_correctly():
    """New 600k-iteration hashes verify correctly."""
    hashed = hash_password("my-secure-pw")
    assert verify_password("my-secure-pw", hashed) is True
    assert verify_password("wrong", hashed) is False


# ── 5. Scheduler snapshot retention cleanup ──────────────────────────────────

async def test_cleanup_old_job_runs_and_snapshots(client):
    """_cleanup_old_job_runs_and_snapshots deletes records older than 90 days."""
    from app.models.ceo_control import SchedulerJobRun

    session, agen = await _get_test_session()
    try:
        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        recent_date = datetime.now(timezone.utc) - timedelta(days=10)

        session.add(SchedulerJobRun(
            organization_id=1, job_name="test_old", status="ok",
            started_at=old_date, finished_at=old_date, duration_ms=100,
            details_json="{}",
        ))
        session.add(SchedulerJobRun(
            organization_id=1, job_name="test_recent", status="ok",
            started_at=recent_date, finished_at=recent_date, duration_ms=200,
            details_json="{}",
        ))
        await session.commit()

        from app.services.sync_scheduler import _cleanup_old_job_runs_and_snapshots
        await _cleanup_old_job_runs_and_snapshots(session, org_id=1)

        from sqlalchemy import select
        remaining = (await session.execute(
            select(SchedulerJobRun).where(SchedulerJobRun.organization_id == 1)
        )).scalars().all()

        assert len(remaining) == 1
        assert remaining[0].job_name == "test_recent"
    finally:
        await agen.aclose()


# ── 6. Idempotency cache cleanup ────────────────────────────────────────────

def test_idempotency_cache_ttl_eviction(monkeypatch):
    """Idempotency cache evicts stale entries on access."""
    from app.core import idempotency

    idempotency._cache.clear()
    try:
        idempotency.store_response("scope", "key1", {"data": "a"})
        assert idempotency.get_cached_response("scope", "key1") is not None

        # Artificially age the entry far past any TTL
        for k in list(idempotency._cache.keys()):
            ts, payload = idempotency._cache[k]
            idempotency._cache[k] = (ts - 100_000, payload)

        # Should be evicted on next access
        assert idempotency.get_cached_response("scope", "key1") is None
    finally:
        idempotency._cache.clear()


# ── 7. Idempotency fingerprint collision on store ─────────────────────────

def test_idempotency_store_rejects_fingerprint_collision():
    """store_response raises IdempotencyConflictError when fingerprints differ."""
    from app.core import idempotency
    from app.core.idempotency import IdempotencyConflictError

    idempotency._cache.clear()
    try:
        idempotency.store_response("scope", "key-fp", {"a": 1}, fingerprint="fp-aaa")
        with pytest.raises(IdempotencyConflictError):
            idempotency.store_response("scope", "key-fp", {"b": 2}, fingerprint="fp-bbb")
    finally:
        idempotency._cache.clear()


def test_idempotency_store_allows_same_fingerprint():
    """store_response allows overwrite when fingerprint matches."""
    from app.core import idempotency

    idempotency._cache.clear()
    try:
        idempotency.store_response("scope", "key-fp2", {"a": 1}, fingerprint="fp-same")
        # Same fingerprint — should not raise
        idempotency.store_response("scope", "key-fp2", {"a": 2}, fingerprint="fp-same")
        cached = idempotency.get_cached_response("scope", "key-fp2", fingerprint="fp-same")
        assert cached is not None
        assert cached["a"] == 2
    finally:
        idempotency._cache.clear()


# ── 8. Password rehash on login ──────────────────────────────────────────

async def test_login_rehashes_old_100k_password(client, monkeypatch):
    """Login with old 100k-iteration hash transparently rehashes to 600k."""
    import base64
    import hashlib
    import os

    session, agen = await _get_test_session()
    try:
        from app.models.user import User

        # Create a user with an old 100k-iteration hash
        password = "OldPassword2026!"
        salt = os.urandom(16)
        iterations = 100_000
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        old_hash = f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"

        user = User(
            id=99, organization_id=1, name="Rehash Test",
            email="rehash@test.com", password_hash=old_hash,
            role="CEO", is_active=True, token_version=1,
        )
        session.add(user)
        await session.commit()

        # Login should succeed
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "rehash@test.com", "password": password},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

        # Fetch the user in a fresh session to see the endpoint's commit
        session2, agen2 = await _get_test_session()
        try:
            from sqlalchemy import select
            refreshed = (await session2.execute(
                select(User).where(User.email == "rehash@test.com")
            )).scalar_one()
            parts = refreshed.password_hash.split("$")
            assert parts[0] == "pbkdf2_sha256"
            assert int(parts[1]) == 600_000

            # Verify the new hash still works
            assert await asyncio.to_thread(verify_password, password, refreshed.password_hash) is True
        finally:
            await agen2.aclose()
    finally:
        await agen.aclose()


# ── 9. replay_job cleanup_snapshots ───────────────────────────────────────

async def test_replay_job_cleanup_snapshots(client):
    """replay_job_for_org('cleanup_snapshots') runs without error."""
    from app.services.sync_scheduler import replay_job_for_org

    session, agen = await _get_test_session()
    try:
        result = await replay_job_for_org(session, org_id=1, job_name="cleanup_snapshots")
        assert result["ok"] is True
        assert result["job_name"] == "cleanup_snapshots"
    finally:
        await agen.aclose()
