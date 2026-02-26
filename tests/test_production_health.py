"""Tests for production health endpoints and startup validation."""
from app.core.config import settings, validate_startup_settings
from app.core.security import create_access_token


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


# ── /health (public, no auth) ────────────────────────────────────────────────


async def test_health_endpoint_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")


# ── /control/health-summary ──────────────────────────────────────────────────


async def test_health_summary_endpoint(client):
    resp = await client.get("/api/v1/control/health-summary", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "open_tasks" in body
    assert "pending_approvals" in body
    assert "connected_integrations" in body


# ── /control/system-health ───────────────────────────────────────────────────


async def test_system_health_endpoint(client):
    resp = await client.get("/api/v1/control/system-health", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] in ("ok", "degraded", "down")
    assert "dependencies" in body


# ── /control/security/posture ────────────────────────────────────────────────


async def test_security_posture_endpoint(client):
    resp = await client.get("/api/v1/control/security/posture", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "needs_attention")


# ── /control/data-quality ────────────────────────────────────────────────────


async def test_data_quality_endpoint(client):
    resp = await client.get("/api/v1/control/data-quality", headers=_ceo_headers())
    assert resp.status_code == 200


# ── /control/storage/metrics ─────────────────────────────────────────────────


async def test_storage_metrics_endpoint(client):
    resp = await client.get("/api/v1/control/storage/metrics", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "ai_router_recent_calls_1h" in body


# ── /control/sla/manager ─────────────────────────────────────────────────────


async def test_manager_sla_endpoint(client):
    resp = await client.get("/api/v1/control/sla/manager", headers=_ceo_headers())
    assert resp.status_code == 200


# ── /control/integrations/health ─────────────────────────────────────────────


async def test_integrations_health_endpoint(client):
    resp = await client.get("/api/v1/control/integrations/health", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "total_connected" in body
    assert "items" in body


# ── validate_startup_settings ────────────────────────────────────────────────


async def test_validate_startup_settings_returns_list():
    issues = validate_startup_settings(settings)
    assert isinstance(issues, list)
