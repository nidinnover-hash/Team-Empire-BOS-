"""Control plane contract — verifies every /control/ endpoint exists, is RBAC-gated,
and returns the documented response model shape.

These tests hit the real FastAPI routes (via httpx) with an in-memory SQLite DB.
They do NOT test business logic — only the API surface contract.
"""

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_headers(role: str = "CEO", org_id: int = 1, user_id: int = 1) -> dict:
    token = create_access_token(
        {"id": user_id, "email": f"{role.lower()}@org1.com", "role": role,
         "org_id": org_id, "token_version": 1, "purpose": "professional"},
    )
    return {"Authorization": f"Bearer {token}"}


STAFF_HEADERS = _make_headers(role="STAFF", user_id=4)
CEO_HEADERS = _make_headers(role="CEO")
MANAGER_HEADERS = _make_headers(role="MANAGER", user_id=3)


# ── Health module ────────────────────────────────────────────────────────────


class TestHealthModule:
    @pytest.mark.asyncio
    async def test_health_summary(self, client: AsyncClient):
        r = await client.get("/api/v1/control/health-summary")
        assert r.status_code == 200
        body = r.json()
        for key in ("open_tasks", "pending_approvals", "connected_integrations",
                     "failing_integrations", "generated_at"):
            assert key in body

    @pytest.mark.asyncio
    async def test_integrations_health(self, client: AsyncClient):
        r = await client.get("/api/v1/control/integrations/health")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total_connected" in body

    @pytest.mark.asyncio
    async def test_system_health(self, client: AsyncClient):
        r = await client.get("/api/v1/control/system-health")
        assert r.status_code == 200
        body = r.json()
        assert body["overall_status"] in ("ok", "degraded", "down")
        assert isinstance(body["dependencies"], list)

    @pytest.mark.asyncio
    async def test_storage_metrics(self, client: AsyncClient):
        r = await client.get("/api/v1/control/storage/metrics")
        assert r.status_code == 200
        body = r.json()
        assert "ai_router_recent_calls_1h" in body

    @pytest.mark.asyncio
    async def test_scheduler_slo(self, client: AsyncClient):
        r = await client.get("/api/v1/control/scheduler/slo")
        assert r.status_code == 200
        body = r.json()
        assert "success_rate" in body
        assert "slo_breached" in body

    @pytest.mark.asyncio
    async def test_webhook_reliability(self, client: AsyncClient):
        r = await client.get("/api/v1/control/webhook/reliability")
        assert r.status_code == 200
        body = r.json()
        assert "total_deliveries" in body

    @pytest.mark.asyncio
    async def test_security_posture(self, client: AsyncClient):
        r = await client.get("/api/v1/control/security/posture")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "needs_attention")

    @pytest.mark.asyncio
    async def test_data_quality(self, client: AsyncClient):
        r = await client.get("/api/v1/control/data-quality")
        assert r.status_code == 200
        body = r.json()
        assert "missing_identity_count" in body

    @pytest.mark.asyncio
    async def test_sla_manager(self, client: AsyncClient):
        r = await client.get("/api/v1/control/sla/manager")
        assert r.status_code == 200
        body = r.json()
        assert "pending_approvals_breached" in body

    @pytest.mark.asyncio
    async def test_trend_metrics(self, client: AsyncClient):
        r = await client.get("/api/v1/control/trend/metrics")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_cron_health(self, client: AsyncClient):
        r = await client.get("/api/v1/control/cron/health")
        assert r.status_code == 200


# ── Compliance module ────────────────────────────────────────────────────────


class TestComplianceModule:
    @pytest.mark.asyncio
    async def test_compliance_report(self, client: AsyncClient):
        r = await client.get("/api/v1/control/compliance/report")
        assert r.status_code == 200
        body = r.json()
        assert "count" in body
        assert "violations" in body

    @pytest.mark.asyncio
    async def test_compliance_run(self, client: AsyncClient):
        r = await client.post("/api/v1/control/compliance/run")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "suggest_only"
        assert "compliance_score" in body


# ── Jobs module ──────────────────────────────────────────────────────────────


class TestJobsModule:
    @pytest.mark.asyncio
    async def test_jobs_runs(self, client: AsyncClient):
        r = await client.get("/api/v1/control/jobs/runs")
        assert r.status_code == 200
        body = r.json()
        assert "count" in body
        assert "items" in body


# ── GitHub maps module ───────────────────────────────────────────────────────


class TestGitHubMapsModule:
    @pytest.mark.asyncio
    async def test_github_identity_map_list(self, client: AsyncClient):
        r = await client.get("/api/v1/control/github-identity-map")
        assert r.status_code == 200
        body = r.json()
        assert "count" in body
        assert "items" in body

    @pytest.mark.asyncio
    async def test_github_identity_map_upsert(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/control/github-identity-map/upsert",
            json={"company_email": "dev@example.com", "github_login": "devuser"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True


# ── CEO module ───────────────────────────────────────────────────────────────


class TestCEOModule:
    @pytest.mark.asyncio
    async def test_ceo_status(self, client: AsyncClient):
        r = await client.get("/api/v1/control/ceo/status")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "suggest_only"

    @pytest.mark.asyncio
    async def test_ceo_morning_brief(self, client: AsyncClient):
        r = await client.get("/api/v1/control/ceo/morning-brief")
        assert r.status_code == 200
        body = r.json()
        assert "priority_actions" in body
        assert body["mode"] == "suggest_only"

    @pytest.mark.asyncio
    async def test_weekly_board_packet(self, client: AsyncClient):
        r = await client.get("/api/v1/control/weekly-board-packet")
        assert r.status_code == 200
        body = r.json()
        assert "compliance" in body
        assert "top_actions" in body

    @pytest.mark.asyncio
    async def test_founder_playbook_today(self, client: AsyncClient):
        r = await client.get("/api/v1/control/founder-playbook/today")
        assert r.status_code == 200
        body = r.json()
        assert "core_values" in body
        assert "today_focus" in body


# ── Platform observability module ────────────────────────────────────────────


class TestPlatformModule:
    @pytest.mark.asyncio
    async def test_signals_recent(self, client: AsyncClient):
        r = await client.get("/api/v1/control/signals/recent")
        assert r.status_code == 200
        body = r.json()
        assert "count" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    @pytest.mark.asyncio
    async def test_signals_recent_with_topic_filter(self, client: AsyncClient):
        r = await client.get("/api/v1/control/signals/recent?topic=execution.completed")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0

    @pytest.mark.asyncio
    async def test_decisions_log(self, client: AsyncClient):
        r = await client.get("/api/v1/control/decisions/log")
        assert r.status_code == 200
        body = r.json()
        assert "count" in body
        assert "items" in body

    @pytest.mark.asyncio
    async def test_decisions_log_with_type_filter(self, client: AsyncClient):
        r = await client.get("/api/v1/control/decisions/log?trace_type=contact.route")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0

    @pytest.mark.asyncio
    async def test_platform_counters(self, client: AsyncClient):
        r = await client.get("/api/v1/control/platform/counters")
        assert r.status_code == 200
        body = r.json()
        assert "signals_24h" in body
        assert "decisions_24h" in body
        assert "topic_counts_24h" in body
        assert "in_process_signal_counts" in body


# ── RBAC enforcement ─────────────────────────────────────────────────────────


class TestRBACEnforcement:
    """STAFF role should be denied on all control endpoints."""

    CONTROL_GET_ENDPOINTS = [
        "/api/v1/control/health-summary",
        "/api/v1/control/integrations/health",
        "/api/v1/control/system-health",
        "/api/v1/control/storage/metrics",
        "/api/v1/control/scheduler/slo",
        "/api/v1/control/webhook/reliability",
        "/api/v1/control/security/posture",
        "/api/v1/control/data-quality",
        "/api/v1/control/sla/manager",
        "/api/v1/control/trend/metrics",
        "/api/v1/control/cron/health",
        "/api/v1/control/compliance/report",
        "/api/v1/control/jobs/runs",
        "/api/v1/control/github-identity-map",
        "/api/v1/control/ceo/status",
        "/api/v1/control/ceo/morning-brief",
        "/api/v1/control/weekly-board-packet",
        "/api/v1/control/founder-playbook/today",
        "/api/v1/control/signals/recent",
        "/api/v1/control/decisions/log",
        "/api/v1/control/platform/counters",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("endpoint", CONTROL_GET_ENDPOINTS)
    async def test_staff_denied_on_get(self, client: AsyncClient, endpoint: str):
        r = await client.get(endpoint, headers=STAFF_HEADERS)
        assert r.status_code == 403, f"{endpoint} should deny STAFF"

    @pytest.mark.asyncio
    async def test_staff_denied_on_compliance_run(self, client: AsyncClient):
        r = await client.post("/api/v1/control/compliance/run", headers=STAFF_HEADERS)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_denied_on_jobs_replay(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/control/jobs/replay",
            json={"job_name": "full_sync"},
            headers=STAFF_HEADERS,
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_allowed_health_summary(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/control/health-summary",
            headers=MANAGER_HEADERS,
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_manager_allowed_platform_counters(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/control/platform/counters",
            headers=MANAGER_HEADERS,
        )
        assert r.status_code == 200


# ── Endpoint inventory ───────────────────────────────────────────────────────


class TestControlPlaneInventory:
    """Verify the control plane has the expected number of route registrations."""

    def test_control_router_has_expected_route_count(self):
        from app.api.v1.endpoints.control import router

        paths = {route.path for route in router.routes if hasattr(route, "path")}
        # Health: 11, Compliance: 3, GitHub: 2, Jobs: 3, Brain: 4, CEO: 5, Platform: 3
        assert len(paths) >= 28, f"Expected >=28 control routes, got {len(paths)}: {sorted(paths)}"

    def test_all_modules_registered(self):
        from app.api.v1.endpoints.control import router

        paths = {route.path for route in router.routes if hasattr(route, "path")}
        # Spot-check that each module contributed routes
        assert any("/health-summary" in p for p in paths), "health module missing"
        assert any("/compliance" in p for p in paths), "compliance module missing"
        assert any("/github-identity-map" in p for p in paths), "github_maps module missing"
        assert any("/jobs" in p for p in paths), "jobs module missing"
        assert any("/brain" in p for p in paths), "brain module missing"
        assert any("/ceo" in p for p in paths), "ceo module missing"
        assert any("/signals" in p for p in paths), "platform signals missing"
        assert any("/decisions" in p for p in paths), "platform decisions missing"
        assert any("/platform/counters" in p for p in paths), "platform counters missing"
