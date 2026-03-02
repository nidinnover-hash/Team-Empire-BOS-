"""
Tests for email endpoints not covered by other test files.

Covers: /auth-url, /health, /inbox, /{email_id}/summarize, /{email_id}/strategize,
and RBAC permission enforcement across email routes.
"""
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.email import Email
from tests.conftest import _make_auth_headers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_email(
    *,
    org_id: int = 1,
    gmail_id: str = "test-gmail-id",
    subject: str = "Test Subject",
    body: str = "Test body text",
    from_address: str = "sender@example.com",
    to_address: str = "ceo@org1.com",
) -> int:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        row = Email(
            organization_id=org_id,
            gmail_id=gmail_id,
            subject=subject,
            body_text=body,
            from_address=from_address,
            to_address=to_address,
            received_at=datetime.now(UTC),
            is_read=False,
            reply_sent=False,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return cast(int, row.id)
    finally:
        await agen.aclose()


# ---------------------------------------------------------------------------
# GET /email/auth-url
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_url_returns_url_and_state(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.email.get_gmail_auth_url",
        lambda state: f"https://accounts.google.com/o/oauth2/v2/auth?state={state}",
    )
    resp = await client.get("/api/v1/email/auth-url")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "state" in data
    assert data["auth_url"].startswith("https://accounts.google.com")


@pytest.mark.asyncio
async def test_auth_url_requires_admin_role(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.email.get_gmail_auth_url",
        lambda state: "https://example.com",
    )
    headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    resp = await client.get("/api/v1/email/auth-url", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /email/health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_returns_status(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.email_service.check_gmail_health",
        AsyncMock(return_value={"status": "ok", "code": None, "email_address": "test@gmail.com", "messages_total": 100, "threads_total": 50}),
    )
    resp = await client.get("/api/v1/email/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["email_address"] == "test@gmail.com"


@pytest.mark.asyncio
async def test_health_requires_admin_role(client, monkeypatch):
    headers = _make_auth_headers(user_id=3, email="manager@org1.com", role="MANAGER", org_id=1)
    resp = await client.get("/api/v1/email/health", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /email/inbox
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inbox_returns_emails(client):
    await _seed_email(gmail_id="inbox-1", subject="First email")
    await _seed_email(gmail_id="inbox-2", subject="Second email")
    resp = await client.get("/api/v1/email/inbox")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_inbox_respects_limit(client):
    for i in range(5):
        await _seed_email(gmail_id=f"limit-{i}", subject=f"Email {i}")
    resp = await client.get("/api/v1/email/inbox?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


@pytest.mark.asyncio
async def test_inbox_respects_offset(client):
    for i in range(5):
        await _seed_email(gmail_id=f"offset-{i}", subject=f"Email {i}")
    all_resp = await client.get("/api/v1/email/inbox?limit=100")
    offset_resp = await client.get("/api/v1/email/inbox?limit=100&offset=2")
    assert len(offset_resp.json()) == len(all_resp.json()) - 2


@pytest.mark.asyncio
async def test_inbox_manager_can_access(client):
    headers = _make_auth_headers(user_id=3, email="manager@org1.com", role="MANAGER", org_id=1)
    resp = await client.get("/api/v1/email/inbox", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inbox_staff_forbidden(client):
    headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    resp = await client.get("/api/v1/email/inbox", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /email/{email_id}/summarize
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_returns_summary(client, monkeypatch):
    email_id = await _seed_email(gmail_id="summarize-1", body="Important update about the project.")
    monkeypatch.setattr(
        "app.services.email_service.summarize_email",
        AsyncMock(return_value="- Project update received\n- Action required"),
    )
    resp = await client.post(f"/api/v1/email/{email_id}/summarize")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email_id"] == email_id
    assert "Project update" in data["summary"]


@pytest.mark.asyncio
async def test_summarize_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.email_service.summarize_email",
        AsyncMock(return_value=None),
    )
    resp = await client.post("/api/v1/email/99999/summarize")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_summarize_staff_forbidden(client):
    headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    resp = await client.post("/api/v1/email/1/summarize", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /email/{email_id}/strategize
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_strategize_returns_strategy(client, monkeypatch):
    email_id = await _seed_email(gmail_id="strat-1", body="Business proposal")
    monkeypatch.setattr(
        "app.services.email_service.strategize_email",
        AsyncMock(return_value="Respond positively and schedule a call."),
    )
    resp = await client.post(f"/api/v1/email/{email_id}/strategize")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email_id"] == email_id
    assert len(data["strategy"]) > 0


@pytest.mark.asyncio
async def test_strategize_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.email_service.strategize_email",
        AsyncMock(side_effect=ValueError("not found")),
    )
    resp = await client.post("/api/v1/email/99999/strategize")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_strategize_ai_failure(client, monkeypatch):
    email_id = await _seed_email(gmail_id="strat-fail-1", body="Test")
    monkeypatch.setattr(
        "app.services.email_service.strategize_email",
        AsyncMock(side_effect=RuntimeError("AI error")),
    )
    resp = await client.post(f"/api/v1/email/{email_id}/strategize")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_strategize_staff_forbidden(client):
    headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    resp = await client.post("/api/v1/email/1/strategize", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Cross-org isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inbox_isolates_by_org(client):
    """Emails from org 2 should not appear in org 1 inbox."""
    await _seed_email(org_id=1, gmail_id="org1-email", subject="Org 1 email")
    await _seed_email(org_id=2, gmail_id="org2-email", subject="Org 2 email")
    resp = await client.get("/api/v1/email/inbox?limit=200")
    assert resp.status_code == 200
    subjects = [e["subject"] for e in resp.json()]
    assert "Org 1 email" in subjects
    assert "Org 2 email" not in subjects


@pytest.mark.asyncio
async def test_summarize_cross_org_rejected(client, monkeypatch):
    """Summarizing an email from another org should return 404."""
    email_id = await _seed_email(org_id=2, gmail_id="cross-org-sum", body="Secret org 2 data")
    monkeypatch.setattr(
        "app.services.email_service.summarize_email",
        AsyncMock(return_value=None),
    )
    resp = await client.post(f"/api/v1/email/{email_id}/summarize")
    assert resp.status_code == 404
