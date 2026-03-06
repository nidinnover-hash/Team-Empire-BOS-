"""Tests for cross-company / multi-org dashboard access control.

Verifies:
1. CEO can access cross-company and executive cockpit endpoints
2. ADMIN can access executive-level (board-packet, status, playbook, morning-brief)
3. ADMIN cannot access cross-company rollup (multi-org cockpit)
4. MANAGER cannot access any CEO cockpit endpoints
5. STAFF cannot access any CEO cockpit endpoints
6. Normal single-org dashboard remains unchanged
"""

import pytest

from app.core.security import create_access_token
from app.core.visibility import (
    can_view_ceo_executive,
    can_view_cross_company,
)

# ── Visibility helpers ────────────────────────────────────────────────────


def test_can_view_cross_company_ceo():
    assert can_view_cross_company("CEO") is True


def test_can_view_cross_company_admin_denied():
    assert can_view_cross_company("ADMIN") is False


def test_can_view_cross_company_manager_denied():
    assert can_view_cross_company("MANAGER") is False


def test_can_view_cross_company_staff_denied():
    assert can_view_cross_company("STAFF") is False


def test_can_view_ceo_executive_ceo():
    assert can_view_ceo_executive("CEO") is True


def test_can_view_ceo_executive_admin():
    assert can_view_ceo_executive("ADMIN") is True


def test_can_view_ceo_executive_manager_denied():
    assert can_view_ceo_executive("MANAGER") is False


def test_can_view_ceo_executive_staff_denied():
    assert can_view_ceo_executive("STAFF") is False


# ── Helper ────────────────────────────────────────────────────────────────


_ROLE_USER_MAP = {"CEO": 1, "ADMIN": 6, "MANAGER": 3, "STAFF": 4}


def _auth(role: str) -> dict[str, str]:
    user_id = _ROLE_USER_MAP[role]
    token = create_access_token(
        {"id": user_id, "email": f"{role.lower()}@org1.com", "role": role,
         "org_id": 1, "token_version": 1},
    )
    return {"Authorization": f"Bearer {token}"}


# ── Cross-company rollup: /cockpit/multi-org (CEO only) ──────────────────


MULTI_ORG_PATH = "/api/v1/control/cockpit/multi-org"


@pytest.mark.asyncio
async def test_multi_org_cockpit_ceo_allowed(client):
    r = await client.get(MULTI_ORG_PATH, headers=_auth("CEO"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_multi_org_cockpit_admin_denied(client):
    r = await client.get(MULTI_ORG_PATH, headers=_auth("ADMIN"))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_multi_org_cockpit_manager_denied(client):
    r = await client.get(MULTI_ORG_PATH, headers=_auth("MANAGER"))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_multi_org_cockpit_staff_denied(client):
    r = await client.get(MULTI_ORG_PATH, headers=_auth("STAFF"))
    assert r.status_code == 403


# ── Executive endpoints: board-packet, ceo/status, playbook (CEO + ADMIN) ──


EXECUTIVE_PATHS = [
    "/api/v1/control/weekly-board-packet",
    "/api/v1/control/ceo/status",
    "/api/v1/control/founder-playbook/today",
    "/api/v1/control/ceo/morning-brief",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", EXECUTIVE_PATHS)
async def test_executive_ceo_allowed(client, path):
    r = await client.get(path, headers=_auth("CEO"))
    assert r.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("path", EXECUTIVE_PATHS)
async def test_executive_admin_allowed(client, path):
    r = await client.get(path, headers=_auth("ADMIN"))
    assert r.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("path", EXECUTIVE_PATHS)
async def test_executive_manager_denied(client, path):
    r = await client.get(path, headers=_auth("MANAGER"))
    assert r.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("path", EXECUTIVE_PATHS)
async def test_executive_staff_denied(client, path):
    r = await client.get(path, headers=_auth("STAFF"))
    assert r.status_code == 403


# ── Normal single-org dashboard KPIs still accessible ────────────────────


@pytest.mark.asyncio
async def test_dashboard_kpis_unchanged_for_ceo(client):
    r = await client.get("/api/v1/dashboard/kpis", headers=_auth("CEO"))
    assert r.status_code == 200
    assert "tasks_pending" in r.json()


@pytest.mark.asyncio
async def test_dashboard_kpis_unchanged_for_manager(client):
    r = await client.get("/api/v1/dashboard/kpis", headers=_auth("MANAGER"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_trends_unchanged_for_ceo(client):
    r = await client.get("/api/v1/dashboard/trends", headers=_auth("CEO"))
    assert r.status_code == 200
    assert "revenue" in r.json()
