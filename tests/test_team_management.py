"""Tests for team management endpoints (role change, toggle active)."""

from __future__ import annotations

import pytest

from tests.conftest import _make_auth_headers

CEO_HEADERS = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
ORG2_HEADERS = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)
MANAGER_HEADERS = _make_auth_headers(3, "manager@org1.com", "MANAGER", 1)

USERS_BASE = "/api/v1/users"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_test_user(client, name="Test User", email="testuser@org1.com", headers=None):
    return await client.post(
        USERS_BASE,
        json={
            "organization_id": 1,
            "name": name,
            "email": email,
            "password": "TestPass123!",
            "role": "STAFF",
        },
        headers=headers or CEO_HEADERS,
    )


# ---------------------------------------------------------------------------
# Role Change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ceo_can_change_role(client):
    resp = await _create_test_user(client, email="role-test@org1.com")
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    resp = await client.patch(
        f"{USERS_BASE}/{user_id}/role",
        json={"role": "MANAGER"},
        headers=CEO_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "MANAGER"


@pytest.mark.asyncio
@pytest.mark.flaky
async def test_non_ceo_cannot_change_role(client):
    resp = await _create_test_user(client, email="role-test2@org1.com")
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    resp = await client.patch(
        f"{USERS_BASE}/{user_id}/role",
        json={"role": "MANAGER"},
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invalid_role_rejected(client):
    resp = await _create_test_user(client, email="role-test3@org1.com")
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    resp = await client.patch(
        f"{USERS_BASE}/{user_id}/role",
        json={"role": "SUPERADMIN"},
        headers=CEO_HEADERS,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Toggle Active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_active(client):
    resp = await _create_test_user(client, email="toggle-test@org1.com")
    assert resp.status_code == 201
    user_id = resp.json()["id"]
    assert resp.json()["is_active"] is True

    # Deactivate
    resp = await client.patch(
        f"{USERS_BASE}/{user_id}/active",
        json={"is_active": False},
        headers=CEO_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Reactivate
    resp = await client.patch(
        f"{USERS_BASE}/{user_id}/active",
        json={"is_active": True},
        headers=CEO_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


# ---------------------------------------------------------------------------
# Cross-org isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_org_role_change_denied(client):
    resp = await _create_test_user(client, email="crossorg-role@org1.com")
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    resp = await client.patch(
        f"{USERS_BASE}/{user_id}/role",
        json={"role": "ADMIN"},
        headers=ORG2_HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_toggle_denied(client):
    resp = await _create_test_user(client, email="crossorg-toggle@org1.com")
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    resp = await client.patch(
        f"{USERS_BASE}/{user_id}/active",
        json={"is_active": False},
        headers=ORG2_HEADERS,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Dashboard KPI endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_kpis(client):
    resp = await client.get("/api/v1/dashboard/kpis", headers=CEO_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks_pending" in data
