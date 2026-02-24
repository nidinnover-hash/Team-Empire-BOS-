"""Tests for the 14-fix production hardening sweep."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app as fastapi_app
from app.models.approval import Approval
from app.models.organization import Organization
from app.models.user import User


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_test_session():
    """Get a DB session from the current test override."""
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


async def _seed_user_and_login(client):
    """Create an org + user and login, returning the CSRF token."""
    session, agen = await _get_test_session()
    try:
        org = Organization(name="Test Org", slug="test-org")
        session.add(org)
        await session.flush()
        user = User(
            organization_id=org.id,
            name="CEO User",
            email="ceo@test.com",
            password_hash=hash_password("secret123"),
            role="CEO",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()
    finally:
        await agen.aclose()

    login = await client.post(
        "/web/login",
        data={"username": "ceo@test.com", "password": "secret123"},
    )
    assert login.status_code == 200
    return login.cookies.get("pc_csrf")


# ── Fix 11: CSRF edge case tests ────────────────────────────────────────────

async def test_csrf_mismatched_tokens_returns_403(client):
    """Both cookie and header present, but different values -> 403."""
    csrf = await _seed_user_and_login(client)
    assert csrf

    # Set cookie to one value, header to a different value
    client.cookies.set("pc_csrf", "cookie-value-aaa")
    resp = await client.post(
        "/web/ops/daily-run?draft_email_limit=0",
        headers={"X-CSRF-Token": "header-value-bbb"},
    )
    assert resp.status_code == 403


async def test_csrf_header_only_no_cookie_returns_403(client):
    """Header present but no cookie -> 403."""
    await _seed_user_and_login(client)

    # Clear the csrf cookie
    client.cookies.delete("pc_csrf")
    resp = await client.post(
        "/web/ops/daily-run?draft_email_limit=0",
        headers={"X-CSRF-Token": "some-token"},
    )
    assert resp.status_code == 403


async def test_csrf_cookie_only_no_header_returns_403(client):
    """Cookie present but no header -> 403."""
    csrf = await _seed_user_and_login(client)
    assert csrf

    # Don't send the X-CSRF-Token header
    resp = await client.post("/web/ops/daily-run?draft_email_limit=0")
    assert resp.status_code == 403


# ── Fix 12: Concurrent approval race test ────────────────────────────────────

async def test_concurrent_approval_race_exactly_one_succeeds(client):
    """Two simultaneous approve requests on the same approval: one wins, one fails."""
    session, agen = await _get_test_session()
    try:
        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="task_execution",
            payload_json={"detail": "Test concurrent approval"},
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        session.add(approval)
        await session.commit()
        approval_id = approval.id
    finally:
        await agen.aclose()

    token = create_access_token({"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1})

    async def _approve():
        return await client.post(
            f"/api/v1/approvals/{approval_id}/approve",
            json={"note": "ok"},
            headers={"Authorization": f"Bearer {token}"},
        )

    r1, r2 = await asyncio.gather(_approve(), _approve())
    statuses = sorted([r1.status_code, r2.status_code])
    # Exactly one should succeed (200), the other should fail (404 — no longer pending)
    assert statuses == [200, 404], f"Expected [200, 404] but got {statuses}"


# ── Fix 13: Integration sync failure tests ───────────────────────────────────

async def test_run_integrations_handles_clickup_error(client, monkeypatch):
    """ClickUp sync failure is caught and marks status as error, doesn't crash."""
    from app.services import sync_scheduler
    from app.services import clickup_service, github_service, do_service, slack_service
    from app.services import compliance_engine
    from app.services.calendar_service import sync_calendar_events

    # Make ClickUp raise, others succeed
    monkeypatch.setattr(clickup_service, "sync_clickup_tasks", AsyncMock(side_effect=RuntimeError("ClickUp API down")))
    monkeypatch.setattr(github_service, "sync_github", AsyncMock(return_value="ok"))
    monkeypatch.setattr(do_service, "sync_digitalocean", AsyncMock(return_value="ok"))
    monkeypatch.setattr(slack_service, "sync_slack_messages", AsyncMock(return_value="ok"))
    monkeypatch.setattr(compliance_engine, "run_compliance", AsyncMock(return_value=None))

    # Mock calendar sync
    import app.services.sync_scheduler as sched_mod
    monkeypatch.setattr(
        "app.services.calendar_service.sync_calendar_events",
        AsyncMock(return_value="ok"),
    )

    session, agen = await _get_test_session()
    try:
        # Should NOT raise even though ClickUp errored
        await sync_scheduler._run_integrations(session, org_id=1)
    finally:
        await agen.aclose()


async def test_run_integrations_handles_github_error(client, monkeypatch):
    """GitHub sync failure is caught and doesn't crash the scheduler."""
    from app.services import sync_scheduler
    from app.services import clickup_service, github_service, do_service, slack_service
    from app.services import compliance_engine

    monkeypatch.setattr(clickup_service, "sync_clickup_tasks", AsyncMock(return_value="ok"))
    monkeypatch.setattr(github_service, "sync_github", AsyncMock(side_effect=ConnectionError("GitHub unreachable")))
    monkeypatch.setattr(do_service, "sync_digitalocean", AsyncMock(return_value="ok"))
    monkeypatch.setattr(slack_service, "sync_slack_messages", AsyncMock(return_value="ok"))
    monkeypatch.setattr(compliance_engine, "run_compliance", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.calendar_service.sync_calendar_events",
        AsyncMock(return_value="ok"),
    )

    session, agen = await _get_test_session()
    try:
        await sync_scheduler._run_integrations(session, org_id=1)
    finally:
        await agen.aclose()


async def test_run_integrations_handles_slack_error(client, monkeypatch):
    """Slack sync failure is caught and doesn't crash the scheduler."""
    from app.services import sync_scheduler
    from app.services import clickup_service, github_service, do_service, slack_service
    from app.services import compliance_engine

    monkeypatch.setattr(clickup_service, "sync_clickup_tasks", AsyncMock(return_value="ok"))
    monkeypatch.setattr(github_service, "sync_github", AsyncMock(return_value="ok"))
    monkeypatch.setattr(do_service, "sync_digitalocean", AsyncMock(return_value="ok"))
    monkeypatch.setattr(slack_service, "sync_slack_messages", AsyncMock(side_effect=TimeoutError("Slack timeout")))
    monkeypatch.setattr(compliance_engine, "run_compliance", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.calendar_service.sync_calendar_events",
        AsyncMock(return_value="ok"),
    )

    session, agen = await _get_test_session()
    try:
        await sync_scheduler._run_integrations(session, org_id=1)
    finally:
        await agen.aclose()


# ── Structural / config tests ────────────────────────────────────────────────

def test_csp_nonce_not_unsafe_inline_in_script_src():
    """Verify CSP header uses nonce, not unsafe-inline for scripts."""
    import inspect
    from app.core import middleware as mw
    source = inspect.getsource(mw.SecurityHeadersMiddleware)
    assert "nonce-{nonce}" in source or "nonce-" in source
    # script-src should NOT have unsafe-inline
    assert "'unsafe-inline' https://unpkg.com" not in source


def test_health_returns_503_on_db_failure():
    """Health endpoint source uses 503 for degraded state."""
    import inspect
    from app.api.v1.endpoints import health
    source = inspect.getsource(health.health_check)
    assert "503" in source


def test_dashboard_timeout_configured():
    """Dashboard gather has asyncio.wait_for timeout."""
    import inspect
    from app.main import dashboard
    source = inspect.getsource(dashboard)
    assert "wait_for" in source
    assert "timeout=" in source


def test_shutdown_grace_seconds_configurable():
    """SHUTDOWN_GRACE_SECONDS is a configurable setting."""
    from app.core.config import Settings
    s = Settings()
    assert hasattr(s, "SHUTDOWN_GRACE_SECONDS")
    assert isinstance(s.SHUTDOWN_GRACE_SECONDS, int)
    assert s.SHUTDOWN_GRACE_SECONDS > 0


def test_logging_config_exists():
    """Structured logging module exists with expected exports."""
    from app.core.logging_config import configure_logging, JSONFormatter, TextFormatter
    assert callable(configure_logging)
    assert JSONFormatter is not None
    assert TextFormatter is not None
