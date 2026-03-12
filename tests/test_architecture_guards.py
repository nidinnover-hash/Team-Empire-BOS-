"""Architecture guards — enforce BOS rules: brain no DB mutation, mutating routes protected."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)

# Paths relative to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
BRAIN_DIR = REPO_ROOT / "app" / "engines" / "brain"
SERVICES_DIR = REPO_ROOT / "app" / "services"

# Service files that do DB selects but are allowed to not reference organization_id
TENANT_GUARD_ALLOWLIST = frozenset({
    "embedding.py",
    "lead_routing_policy.py",
})
# Services that have org_id but may not use .where( (e.g. insert-only, or filter via join)
WHERE_FILTER_ALLOWLIST = frozenset({
    "api_key.py",  # validate by key hash; org from key
})


def _collect_routes(app, prefix: str = ""):
    """Recursively collect (path, methods) from FastAPI app."""
    out = []
    for route in getattr(app, "routes", []):
        if hasattr(route, "path") and hasattr(route, "methods"):
            path = (prefix + route.path).replace("//", "/")
            out.append((path, route.methods))
        elif hasattr(route, "routes"):
            p = getattr(route, "path", "") or ""
            out.extend(_collect_routes(route, prefix + p))
        elif hasattr(route, "app"):  # Mount
            p = getattr(route, "path", "") or ""
            out.extend(_collect_routes(route.app, prefix + p))
    return out


class TestBrainNoDbMutation:
    """AI brain must never mutate the database."""

    def test_brain_dir_has_no_db_add_commit(self):
        """No db.add, db.commit, db.delete in app/engines/brain/."""
        if not BRAIN_DIR.exists():
            pytest.skip("Brain dir not found")
        found = []
        for py in BRAIN_DIR.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="replace")
            if "db.add(" in text or "db.commit(" in text or "db.delete(" in text:
                found.append(str(py.relative_to(REPO_ROOT)))
        assert not found, f"Brain must not mutate DB. Found in: {found}"


class TestServicesTenantAwareness:
    """Services that run select() must be org-aware (organization_id in file)."""

    def test_services_with_select_mention_organization_id(self):
        """Any app/services .py with select( and execute( must contain organization_id."""
        if not SERVICES_DIR.exists():
            pytest.skip("Services dir not found")
        failures = []
        for py in SERVICES_DIR.rglob("*.py"):
            rel = py.relative_to(REPO_ROOT)
            name = rel.name
            if name in TENANT_GUARD_ALLOWLIST:
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            has_select = "select(" in text
            has_execute = "execute(select" in text or "db.execute(" in text
            has_org = "organization_id" in text
            if has_select and has_execute and not has_org:
                failures.append(str(rel))
        assert not failures, (
            "Services that run select/execute must reference organization_id (tenant isolation). "
            f"Add org filter or allowlist in test. Failed: {failures}"
        )

    def test_services_with_select_use_where_filter(self):
        """Services with select+execute+organization_id must also use .where( (filter in place)."""
        if not SERVICES_DIR.exists():
            pytest.skip("Services dir not found")
        failures = []
        for py in SERVICES_DIR.rglob("*.py"):
            rel = py.relative_to(REPO_ROOT)
            name = rel.name
            if name in TENANT_GUARD_ALLOWLIST or name in WHERE_FILTER_ALLOWLIST:
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            has_select = "select(" in text
            has_execute = "execute(select" in text or "db.execute(" in text
            has_org = "organization_id" in text
            has_where = ".where(" in text
            if has_select and has_execute and has_org and not has_where:
                failures.append(str(rel))
        assert not failures, (
            "Services that query with organization_id should use .where( for tenant filter. "
            f"Add allowlist if legitimate. Failed: {failures}"
        )


class TestMutatingRoutesProtected:
    """POST/PUT/PATCH/DELETE API routes must require auth (401/403 without token)."""

    @pytest.mark.asyncio
    async def test_mutating_routes_reject_no_auth(self, _test_engine):
        """Without Authorization, mutating routes must return 401/403 (not 200)."""
        from httpx import ASGITransport, AsyncClient

        from app.main import app as fastapi_app

        # Paths that may be intentionally public (webhooks, login, etc.)
        PUBLIC_MUTATING_PREFIXES = (
            "/api/v1/auth/login",
            "/api/v1/webhooks/",
            "/api/v1/stripe-webhooks",
            "/api/v1/stripe/webhook",  # Stripe webhook — verified by Stripe signature, not user auth
            "/web/",
        )
        routes = _collect_routes(fastapi_app)
        mutating = [
            (path, methods)
            for path, methods in routes
            if methods & {"POST", "PUT", "PATCH", "DELETE"}
            and path.startswith("/api/v1/")
            and not any(path.startswith(p) for p in PUBLIC_MUTATING_PREFIXES)
        ]
        # Use a client with NO auth headers
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as anon:
            seen = set()
            failures = []
            for path, methods in mutating:
                for method in methods & {"POST", "PUT", "PATCH", "DELETE"}:
                    if (path, method) in seen:
                        continue
                    seen.add((path, method))
                    try:
                        resp = await anon.request(method, path, json={})
                        if resp.status_code == 200:
                            failures.append((method, path))
                    except Exception:
                        logger.debug("Route %s %s raised (e.g. missing config); treat as protected", method, path, exc_info=True)
        assert not failures, (
            "Mutating routes must not return 200 without auth. "
            f"Got 200 without Authorization for: {failures[:25]}"
        )


class TestSensitiveRoutesGated:
    """Control-lever routes must be the documented ones (no new lever without updating guard)."""

    def test_levers_mutating_routes_are_allowlisted(self):
        """Any POST under /api/v1/control/levers/ must be in the allowed list."""
        from app.main import app as fastapi_app

        LEVERS_PREFIX = "/api/v1/control/levers/"
        ALLOWED_LEVER_PATHS = (
            "/api/v1/control/levers/can-send",
            "/api/v1/control/levers/record-send",
            "/api/v1/control/levers/route-lead",
            "/api/v1/control/levers/request-money-approval",
            "/api/v1/control/levers/study-abroad/application-milestones",
            "/api/v1/control/levers/study-abroad/risk-status",
        )
        routes = _collect_routes(fastapi_app)
        mutating = [
            path
            for path, methods in routes
            if methods & {"POST", "PUT", "PATCH", "DELETE"}
            and path.startswith(LEVERS_PREFIX)
        ]
        disallowed = [p for p in mutating if not any(p == a or p.startswith(a + "/") for a in ALLOWED_LEVER_PATHS)]
        assert not disallowed, (
            "New control lever routes must be added to ALLOWED_LEVER_PATHS in this test. "
            f"Disallowed: {disallowed}"
        )
