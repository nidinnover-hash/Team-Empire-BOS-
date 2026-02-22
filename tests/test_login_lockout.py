"""
Tests for per-IP login brute-force lockout.

The lockout tracker lives in app.core.middleware._login_failures (an in-memory
sliding-window deque).  Each test clears it so failures from one test don't
bleed into the next (the ASGI transport reports request.client as None,
so every attempt resolves to the "unknown" bucket).
"""
import pytest_asyncio

from app.core.middleware import _login_failures, LOGIN_FAIL_MAX


@pytest_asyncio.fixture(autouse=True)
async def clear_login_failures():
    """Wipe the in-memory failure tracker before AND after each test."""
    _login_failures.clear()
    yield
    _login_failures.clear()


# ── /token (OAuth2 form endpoint) ────────────────────────────────────────────

async def test_single_bad_login_returns_401(client):
    r = await client.post("/token", data={"username": "bad@example.com", "password": "wrong"})
    assert r.status_code == 401


async def test_lockout_after_max_failures_on_token_endpoint(client):
    """After LOGIN_FAIL_MAX bad attempts the next attempt returns 429."""
    for _ in range(LOGIN_FAIL_MAX):
        r = await client.post("/token", data={"username": "bad@ai.com", "password": "x"})
        assert r.status_code == 401

    r = await client.post("/token", data={"username": "bad@ai.com", "password": "x"})
    assert r.status_code == 429


async def test_lockout_message_is_descriptive(client):
    for _ in range(LOGIN_FAIL_MAX):
        await client.post("/token", data={"username": "bad@ai.com", "password": "x"})

    r = await client.post("/token", data={"username": "bad@ai.com", "password": "x"})
    assert "Too many failed" in r.json()["detail"]


# ── /web/login (cookie-based web login) ──────────────────────────────────────

async def test_lockout_after_max_failures_on_web_login(client):
    for _ in range(LOGIN_FAIL_MAX):
        r = await client.post("/web/login", data={"username": "bad@ai.com", "password": "x"})
        assert r.status_code == 401

    r = await client.post("/web/login", data={"username": "bad@ai.com", "password": "x"})
    assert r.status_code == 429


# ── /api/v1/auth/login (Bearer-token auth router) ───────────────────────────

async def test_lockout_after_max_failures_on_auth_router(client):
    for _ in range(LOGIN_FAIL_MAX):
        r = await client.post(
            "/api/v1/auth/login",
            data={"username": "bad@ai.com", "password": "x"},
        )
        assert r.status_code == 401

    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "bad@ai.com", "password": "x"},
    )
    assert r.status_code == 429


# ── Boundary / accumulation behaviour ────────────────────────────────────────

async def test_failure_below_max_is_still_allowed(client):
    """LOGIN_FAIL_MAX - 1 failures must not trigger lockout."""
    for _ in range(LOGIN_FAIL_MAX - 1):
        await client.post("/token", data={"username": "bad@ai.com", "password": "x"})

    # Exactly one under the limit — should still get 401, not 429
    r = await client.post("/token", data={"username": "bad@ai.com", "password": "x"})
    assert r.status_code == 401


async def test_10th_failure_recorded_then_11th_is_blocked(client):
    """Failures accumulate: 10th returns 401, 11th returns 429."""
    for _ in range(LOGIN_FAIL_MAX - 1):
        await client.post("/token", data={"username": "bad@ai.com", "password": "x"})

    # 10th attempt — bucket goes from 9 → 10
    r = await client.post("/token", data={"username": "bad@ai.com", "password": "x"})
    assert r.status_code == 401

    # 11th attempt — bucket is now 10, check_login_allowed returns False
    r = await client.post("/token", data={"username": "bad@ai.com", "password": "x"})
    assert r.status_code == 429


async def test_cross_endpoint_failures_share_bucket(client):
    """Failures from /token and /web/login share the same 'unknown' IP bucket."""
    half = LOGIN_FAIL_MAX // 2
    for _ in range(half):
        await client.post("/token", data={"username": "bad@ai.com", "password": "x"})
    for _ in range(LOGIN_FAIL_MAX - half):
        await client.post("/web/login", data={"username": "bad@ai.com", "password": "x"})

    # All LOGIN_FAIL_MAX failures have been recorded — next call is locked out
    r = await client.post("/token", data={"username": "bad@ai.com", "password": "x"})
    assert r.status_code == 429
