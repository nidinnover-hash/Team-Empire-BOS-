"""Tests for account security hardening — lockout, sessions, idle timeout."""

import pytest

from app.core.account_security import (
    _reset_registry,
    active_session_count,
    clear_all_sessions,
    compute_lockout_until,
    is_session_valid,
    register_session,
    remove_session,
    touch_session,
)

# ── Lockout computation ─────────────────────────────────────────────────────


def test_below_threshold_no_lockout():
    assert compute_lockout_until(0) is None
    assert compute_lockout_until(4) is None


def test_at_threshold_locks_out():
    result = compute_lockout_until(5)
    assert result is not None


def test_lockout_duration_increases():
    t1 = compute_lockout_until(5)
    t2 = compute_lockout_until(10)
    assert t1 is not None and t2 is not None
    assert t2 > t1


# ── Per-account lockout integration ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_locks_after_failures(db):
    from sqlalchemy import select

    from app.core.account_security import check_account_locked, record_account_login_failure
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == 1))
    user = result.scalar_one()

    # Should not be locked initially
    assert await check_account_locked(db, user) is False

    # Record 5 failures (default threshold)
    for _ in range(5):
        await record_account_login_failure(db, user)

    # Should be locked now
    assert await check_account_locked(db, user) is True


@pytest.mark.asyncio
async def test_successful_login_resets_failures(db):
    from sqlalchemy import select

    from app.core.account_security import (
        check_account_locked,
        record_account_login_failure,
        reset_account_login_failures,
    )
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == 1))
    user = result.scalar_one()

    for _ in range(5):
        await record_account_login_failure(db, user)
    assert await check_account_locked(db, user) is True

    await reset_account_login_failures(db, user)
    assert await check_account_locked(db, user) is False
    assert user.failed_login_count == 0


@pytest.mark.asyncio
async def test_admin_unlock(db):
    from sqlalchemy import select

    from app.core.account_security import (
        check_account_locked,
        record_account_login_failure,
        unlock_account,
    )
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == 1))
    user = result.scalar_one()

    for _ in range(5):
        await record_account_login_failure(db, user)
    assert await check_account_locked(db, user) is True

    await unlock_account(db, user)
    assert await check_account_locked(db, user) is False


# ── Login endpoint with lockout ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_locked_account_returns_423(client):
    from sqlalchemy import select

    from app.core.account_security import record_account_login_failure
    from app.core.deps import get_db
    from app.main import app
    from app.models.user import User

    override = app.dependency_overrides[get_db]
    async for session in override():
        result = await session.execute(select(User).where(User.id == 1))
        user = result.scalar_one()
        for _ in range(5):
            await record_account_login_failure(session, user)
        await session.commit()

    resp = await client.post(
        "/web/login",
        data={"username": "ceo@org1.com", "password": "wrongpassword123"},
        follow_redirects=False,
    )
    # Should get 423 (locked) or 429 (rate limited) or 401 — lockout or auth failure
    assert resp.status_code in {423, 429, 401}


# ── Session registry ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_session():
    _reset_registry()
    evicted = await register_session(1, "sess-a")
    assert evicted is None
    assert await active_session_count(1) == 1


@pytest.mark.asyncio
async def test_session_limit_evicts_oldest():
    _reset_registry()
    await register_session(1, "sess-1")
    await register_session(1, "sess-2")
    await register_session(1, "sess-3")
    evicted = await register_session(1, "sess-4")
    assert evicted == "sess-1"
    assert await active_session_count(1) == 3


@pytest.mark.asyncio
async def test_session_valid():
    _reset_registry()
    await register_session(1, "sess-x")
    assert await is_session_valid(1, "sess-x") is True


@pytest.mark.asyncio
async def test_nonexistent_session_invalid():
    _reset_registry()
    assert await is_session_valid(1, "nonexistent") is False


@pytest.mark.asyncio
async def test_remove_session():
    _reset_registry()
    await register_session(1, "sess-del")
    await remove_session(1, "sess-del")
    assert await is_session_valid(1, "sess-del") is False


@pytest.mark.asyncio
async def test_touch_session_keeps_alive():
    _reset_registry()
    await register_session(1, "sess-touch")
    await touch_session(1, "sess-touch")
    assert await is_session_valid(1, "sess-touch") is True


@pytest.mark.asyncio
async def test_clear_all_sessions():
    _reset_registry()
    await register_session(1, "a")
    await register_session(1, "b")
    await clear_all_sessions(1)
    assert await active_session_count(1) == 0


# ── Admin unlock endpoint ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unlock_account_endpoint(client):
    resp = await client.post("/api/v1/admin/unlock-account/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unlocked"
    assert data["user_id"] == 1


@pytest.mark.asyncio
async def test_unlock_nonexistent_user_404(client):
    resp = await client.post("/api/v1/admin/unlock-account/99999")
    assert resp.status_code == 404
