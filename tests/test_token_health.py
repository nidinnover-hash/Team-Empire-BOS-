"""Tests for app/services/token_health.py — token health checks and rotation."""
from datetime import UTC, datetime, timedelta

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.event import Event
from app.models.integration import Integration
from app.services.token_health import (
    check_token_health,
    get_rotation_report,
    rotate_oauth_token,
)


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


# ── check_token_health ────────────────────────────────────────────────────────


async def test_check_token_health_empty(client):
    """No integrations returns empty list."""
    session, agen = await _get_session()
    try:
        result = await check_token_health(session, organization_id=1)
        assert isinstance(result, list)
    finally:
        await agen.aclose()


async def test_check_token_health_oauth_healthy(client):
    """Gmail integration with refresh_token is healthy."""
    session, agen = await _get_session()
    try:
        row = Integration(
            organization_id=1,
            type="gmail",
            status="connected",
            config_json={"access_token": "tok", "refresh_token": "rft"},
        )
        session.add(row)
        await session.commit()

        items = await check_token_health(session, organization_id=1)
        gmail = next((i for i in items if i["type"] == "gmail"), None)
        assert gmail is not None
        assert gmail["status"] == "healthy"
        assert gmail["token_type"] == "oauth"
    finally:
        await agen.aclose()


async def test_check_token_health_oauth_no_refresh_token(client):
    """OAuth without refresh_token gets warning."""
    session, agen = await _get_session()
    try:
        row = Integration(
            organization_id=1,
            type="google_calendar",
            status="connected",
            config_json={"access_token": "tok"},
        )
        session.add(row)
        await session.commit()

        items = await check_token_health(session, organization_id=1)
        gcal = next((i for i in items if i["type"] == "google_calendar"), None)
        assert gcal is not None
        assert gcal["status"] == "warning"
        assert "refresh_token" in str(gcal["recommendation"]).lower()
    finally:
        await agen.aclose()


async def test_check_token_health_oauth_expired(client):
    """OAuth with expired token returns expired status."""
    session, agen = await _get_session()
    try:
        expired = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        row = Integration(
            organization_id=1,
            type="gmail",
            status="connected",
            config_json={
                "access_token": "tok",
                "refresh_token": "rft",
                "expires_at": expired,
            },
        )
        session.add(row)
        await session.commit()

        items = await check_token_health(session, organization_id=1)
        gmail = next((i for i in items if i["type"] == "gmail"), None)
        assert gmail is not None
        assert gmail["status"] == "expired"
    finally:
        await agen.aclose()


async def test_check_token_health_oauth_expiring_soon(client):
    """OAuth expiring within 1 hour gets expiring_soon status."""
    session, agen = await _get_session()
    try:
        soon = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
        row = Integration(
            organization_id=1,
            type="gmail",
            status="connected",
            config_json={
                "access_token": "tok",
                "refresh_token": "rft",
                "expires_at": soon,
            },
        )
        session.add(row)
        await session.commit()

        items = await check_token_health(session, organization_id=1)
        gmail = next((i for i in items if i["type"] == "gmail"), None)
        assert gmail is not None
        assert gmail["status"] == "expiring_soon"
    finally:
        await agen.aclose()


async def test_check_token_health_pat_stale(client):
    """PAT older than 90 days is flagged as stale."""
    session, agen = await _get_session()
    try:
        row = Integration(
            organization_id=1,
            type="github",
            status="connected",
            config_json={"access_token": "ghp_xxx"},
        )
        row.updated_at = datetime.now(UTC) - timedelta(days=100)
        session.add(row)
        await session.commit()

        items = await check_token_health(session, organization_id=1)
        gh = next((i for i in items if i["type"] == "github"), None)
        assert gh is not None
        assert gh["status"] == "stale"
        assert gh["token_type"] == "pat"
    finally:
        await agen.aclose()


async def test_check_token_health_pat_healthy(client):
    """Fresh PAT is healthy."""
    session, agen = await _get_session()
    try:
        row = Integration(
            organization_id=1,
            type="clickup",
            status="connected",
            config_json={"access_token": "pk_xxx"},
        )
        row.updated_at = datetime.now(UTC)
        session.add(row)
        await session.commit()

        items = await check_token_health(session, organization_id=1)
        cu = next((i for i in items if i["type"] == "clickup"), None)
        assert cu is not None
        assert cu["status"] == "healthy"
    finally:
        await agen.aclose()


# ── rotate_oauth_token ────────────────────────────────────────────────────────


async def test_rotate_no_integration(client):
    """Rotation with no integration returns error."""
    session, agen = await _get_session()
    try:
        result = await rotate_oauth_token(session, 1, "gmail")
        assert result["ok"] is False
        assert "not found" in str(result["error"]).lower() or "no connected" in str(result["error"]).lower()
    finally:
        await agen.aclose()


async def test_rotate_non_oauth_type(client):
    """Rotation for non-OAuth type returns error."""
    session, agen = await _get_session()
    try:
        row = Integration(
            organization_id=1,
            type="github",
            status="connected",
            config_json={"access_token": "ghp_xxx"},
        )
        session.add(row)
        await session.commit()

        result = await rotate_oauth_token(session, 1, "github")
        assert result["ok"] is False
        assert "not an oauth" in str(result["error"]).lower()
    finally:
        await agen.aclose()


async def test_rotate_no_refresh_token(client):
    """Rotation without refresh_token returns error."""
    session, agen = await _get_session()
    try:
        row = Integration(
            organization_id=1,
            type="gmail",
            status="connected",
            config_json={"access_token": "tok"},
        )
        session.add(row)
        await session.commit()

        result = await rotate_oauth_token(session, 1, "gmail")
        assert result["ok"] is False
        assert "refresh_token" in str(result["error"]).lower()
    finally:
        await agen.aclose()


async def test_rotate_oauth_success(client, monkeypatch):
    """Successful OAuth token refresh updates integration config."""
    from unittest.mock import MagicMock

    session, agen = await _get_session()
    try:
        row = Integration(
            organization_id=1,
            type="gmail",
            status="connected",
            config_json={"access_token": "old_tok", "refresh_token": "rft_123"},
        )
        session.add(row)
        await session.commit()

        fake_refresh = MagicMock(return_value={
            "access_token": "new_tok",
            "expires_in": 3600,
            "expires_at": "2026-02-27T00:00:00+00:00",
        })
        monkeypatch.setattr("app.tools.gmail.refresh_access_token", fake_refresh)

        result = await rotate_oauth_token(session, 1, "gmail")
        assert result["ok"] is True
        assert result["type"] == "gmail"
        assert "refreshed_at" in result
        fake_refresh.assert_called_once_with("rft_123")
    finally:
        await agen.aclose()


async def test_rotate_oauth_refresh_fails(client, monkeypatch):
    """OAuth refresh that raises exception returns error gracefully."""
    session, agen = await _get_session()
    try:
        row = Integration(
            organization_id=1,
            type="gmail",
            status="connected",
            config_json={"access_token": "old_tok", "refresh_token": "rft_bad"},
        )
        session.add(row)
        await session.commit()

        def _fail_refresh(rt):
            raise RuntimeError("Google API error")

        monkeypatch.setattr("app.tools.gmail.refresh_access_token", _fail_refresh)

        result = await rotate_oauth_token(session, 1, "gmail")
        assert result["ok"] is False
        assert "failed" in result["error"].lower() or "rotation" in result["error"].lower()
    finally:
        await agen.aclose()


# ── get_rotation_report ───────────────────────────────────────────────────────


async def test_get_rotation_report_structure(client):
    """Rotation report has expected structure."""
    session, agen = await _get_session()
    try:
        report = await get_rotation_report(session, organization_id=1)
        assert "generated_at" in report
        assert "total_integrations" in report
        assert "healthy" in report
        assert "warnings" in report
        assert "critical" in report
        assert "rotation_overdue" in report
        assert "rotation_due_soon" in report
        assert "manual_required" in report
        assert "items" in report
    finally:
        await agen.aclose()


# ── API endpoint tests ────────────────────────────────────────────────────────


async def test_token_health_endpoint(client):
    """GET /integrations/token-health returns report."""
    resp = await client.get("/api/v1/integrations/token-health", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "generated_at" in body
    assert "items" in body


async def test_security_center_endpoint(client):
    """GET /integrations/security-center returns actionable security snapshot."""
    resp = await client.get("/api/v1/integrations/security-center", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "risk_level" in body
    assert "summary" in body
    assert "next_actions" in body


async def test_security_center_trend_endpoint(client):
    """GET /integrations/security-center/trend returns org-shared history points."""
    first = await client.get("/api/v1/integrations/security-center", headers=_ceo_headers())
    assert first.status_code == 200
    second = await client.get("/api/v1/integrations/security-center", headers=_ceo_headers())
    assert second.status_code == 200

    trend = await client.get("/api/v1/integrations/security-center/trend?limit=14", headers=_ceo_headers())
    assert trend.status_code == 200
    body = trend.json()
    assert "points" in body
    assert isinstance(body["points"], list)
    if body["points"]:
        point = body["points"][-1]
        assert "timestamp" in point
        assert "risk_score" in point
        assert "risk_level" in point


async def test_security_center_trend_limit_and_ordering(client):
    session, agen = await _get_session()
    try:
        base = datetime.now(UTC) - timedelta(minutes=10)
        for idx in range(5):
            session.add(
                Event(
                    organization_id=1,
                    event_type="integrations_security_center_viewed",
                    actor_user_id=1,
                    entity_type="integration_security",
                    entity_id=None,
                    payload_json={"risk_score": idx, "risk_level": "low"},
                    created_at=base + timedelta(minutes=idx),
                )
            )
        await session.commit()
        trend = await client.get("/api/v1/integrations/security-center/trend?limit=3", headers=_ceo_headers())
        assert trend.status_code == 200
        points = trend.json()["points"]
        assert len(points) == 3
        assert [int(p["risk_score"]) for p in points] == [2, 3, 4]
        parsed = [datetime.fromisoformat(str(p["timestamp"]).replace("Z", "+00:00")) for p in points]
        assert parsed[0] <= parsed[1] <= parsed[2]
    finally:
        await agen.aclose()
