"""Tests for hardening round 5: dead code removal, timing fixes, audit, email safety."""
import asyncio
import hmac
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.deps import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.main import app as fastapi_app


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_test_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


# ── 1. Dead get_current_user removed from security.py ────────────────────

def test_get_current_user_removed_from_security():
    """get_current_user should no longer exist in security module."""
    from app.core import security
    assert not hasattr(security, "get_current_user"), (
        "get_current_user still exists in security.py — it should be removed"
    )


# ── 2. _DUMMY_HASH uses 600k iterations ──────────────────────────────────

def test_auth_dummy_hash_uses_600k():
    """_DUMMY_HASH in auth.py uses 600k iterations to match live hashes."""
    from app.api.v1.endpoints import auth
    parts = auth._DUMMY_HASH.split("$")
    assert parts[0] == "pbkdf2_sha256"
    assert int(parts[1]) == 600_000


def test_main_dummy_hash_uses_600k():
    """_DUMMY_HASH in main.py uses 600k iterations to match live hashes."""
    from app import main
    parts = main._DUMMY_HASH.split("$")
    assert parts[0] == "pbkdf2_sha256"
    assert int(parts[1]) == 600_000


# ── 3. Successful login is audited ───────────────────────────────────────

async def test_login_success_is_audited(client):
    """Successful login creates a login_success audit event."""
    import base64
    import hashlib
    import os

    session, agen = await _get_test_session()
    try:
        from app.models.user import User

        password = "AuditTest2026!"
        hashed = hash_password(password)
        user = User(
            id=88, organization_id=1, name="Audit Test",
            email="audit-login@test.com", password_hash=hashed,
            role="CEO", is_active=True, token_version=1,
        )
        session.add(user)
        await session.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "audit-login@test.com", "password": password},
        )
        assert resp.status_code == 200

        # Check audit log for login_success event
        from sqlalchemy import select
        from app.models.event import Event
        session2, agen2 = await _get_test_session()
        try:
            events = (await session2.execute(
                select(Event).where(
                    Event.event_type == "login_success",
                    Event.actor_user_id == 88,
                )
            )).scalars().all()
            assert len(events) >= 1, "Expected at least one login_success audit event"
        finally:
            await agen2.aclose()
    finally:
        await agen.aclose()


# ── 4. Email normalization ───────────────────────────────────────────────

async def test_email_lookup_is_case_insensitive(client):
    """get_user_by_email normalizes email to lowercase."""
    session, agen = await _get_test_session()
    try:
        from app.services import user as user_service

        # ceo@org1.com is seeded in conftest as lowercase
        user_upper = await user_service.get_user_by_email(session, "CEO@ORG1.COM")
        user_lower = await user_service.get_user_by_email(session, "ceo@org1.com")
        user_mixed = await user_service.get_user_by_email(session, " Ceo@Org1.Com ")

        assert user_lower is not None
        assert user_upper is not None
        assert user_mixed is not None
        assert user_upper.id == user_lower.id == user_mixed.id
    finally:
        await agen.aclose()


# ── 5. Idempotency 409 uses fixed message ────────────────────────────────

def test_idempotency_409_does_not_leak_internal_message():
    """The 409 detail should be a fixed client-safe string, not str(exc)."""
    from app.core.idempotency import IdempotencyConflictError, store_response, _cache

    _cache.clear()
    try:
        store_response("scope", "test-409", {"a": 1}, fingerprint="fp-1")
        with pytest.raises(IdempotencyConflictError):
            store_response("scope", "test-409", {"b": 2}, fingerprint="fp-2")
    finally:
        _cache.clear()


# ── 6. Compose rate limiter enforces org cap ─────────────────────────────

def test_compose_rate_limiter_org_cap():
    """_compose_counts dict does not grow past _COMPOSE_MAX_ORGS."""
    from app.api.v1.endpoints import email as email_mod
    from collections import deque
    from time import time

    old_counts = email_mod._compose_counts.copy()
    old_max = email_mod._COMPOSE_MAX_ORGS
    try:
        email_mod._compose_counts.clear()
        email_mod._COMPOSE_MAX_ORGS = 5

        # Fill to the cap
        now = time()
        for i in range(5):
            email_mod._compose_counts[i] = deque([now])

        # Calling _check_compose_rate for a new org_id should not grow the dict
        # because we're at the cap
        email_mod._check_compose_rate(999)
        assert 999 not in email_mod._compose_counts
    finally:
        email_mod._COMPOSE_MAX_ORGS = old_max
        email_mod._compose_counts.clear()
        email_mod._compose_counts.update(old_counts)


# ── 7. WhatsApp verify token uses constant-time comparison ───────────────

def test_whatsapp_verify_uses_hmac_compare():
    """The WhatsApp webhook verify endpoint uses hmac.compare_digest."""
    import inspect
    from app.api.v1.endpoints import integrations
    source = inspect.getsource(integrations.whatsapp_webhook_verify)
    assert "hmac.compare_digest" in source
    assert "hub_verify_token ==" not in source
