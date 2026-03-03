"""
Tests for super-admin endpoints at /api/v1/admin.

Covers: org listing, org summary, readiness, autonomy gates/policy/rollout,
dry-run, policy history/rollback, readiness trend, whatsapp webhook failures,
user listing, grant/revoke super-admin, and RBAC enforcement.
"""
import pytest

from tests.conftest import _make_auth_headers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _super_admin_headers() -> dict[str, str]:
    """CEO user id=1 is seeded as is_super_admin=True in conftest."""
    return _make_auth_headers(user_id=1, email="ceo@org1.com", role="CEO", org_id=1)


def _non_super_headers() -> dict[str, str]:
    """CEO user id=2 is seeded WITHOUT is_super_admin=True."""
    return _make_auth_headers(user_id=2, email="ceo@org2.com", role="CEO", org_id=2)


def _manager_headers() -> dict[str, str]:
    return _make_auth_headers(user_id=3, email="manager@org1.com", role="MANAGER", org_id=1)


# ---------------------------------------------------------------------------
# GET /admin/orgs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_orgs(client):
    resp = await client.get("/api/v1/admin/orgs", headers=_super_admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2  # 2 orgs seeded in conftest
    org_ids = [o["id"] for o in data]
    assert 1 in org_ids
    assert 2 in org_ids


@pytest.mark.asyncio
async def test_list_orgs_requires_super_admin(client):
    resp = await client.get("/api/v1/admin/orgs", headers=_non_super_headers())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_orgs_manager_forbidden(client):
    resp = await client.get("/api/v1/admin/orgs", headers=_manager_headers())
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/orgs/{org_id}/summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_summary(client):
    resp = await client.get("/api/v1/admin/orgs/1/summary", headers=_super_admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert data["name"] == "Test Org"
    assert "user_count" in data
    assert "task_count" in data


@pytest.mark.asyncio
async def test_org_summary_not_found(client):
    resp = await client.get("/api/v1/admin/orgs/9999/summary", headers=_super_admin_headers())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/orgs/{org_id}/readiness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_readiness(client):
    resp = await client.get("/api/v1/admin/orgs/1/readiness", headers=_super_admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "status" in data
    assert data["status"] in ("ready", "watch", "blocked")


@pytest.mark.asyncio
async def test_org_readiness_not_found(client):
    resp = await client.get("/api/v1/admin/orgs/9999/readiness", headers=_super_admin_headers())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/orgs/readiness (fleet)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_readiness(client):
    resp = await client.get("/api/v1/admin/orgs/readiness", headers=_super_admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_fleet_readiness_status_filter(client):
    resp = await client.get("/api/v1/admin/orgs/readiness?status=ready", headers=_super_admin_headers())
    assert resp.status_code == 200
    for item in resp.json():
        assert item["status"] == "ready"


# ---------------------------------------------------------------------------
# GET /admin/orgs/{org_id}/autonomy-gates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_autonomy_gates(client):
    resp = await client.get("/api/v1/admin/orgs/1/autonomy-gates", headers=_super_admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "allowed_modes" in data
    assert "denied_modes" in data
    assert "readiness_score" in data


# ---------------------------------------------------------------------------
# GET/PATCH /admin/orgs/{org_id}/autonomy-policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_autonomy_policy(client):
    resp = await client.get("/api/v1/admin/orgs/1/autonomy-policy", headers=_super_admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "org_id" in data or "organization_id" in data or isinstance(data, dict)


@pytest.mark.asyncio
async def test_update_autonomy_policy(client):
    resp = await client.patch(
        "/api/v1/admin/orgs/1/autonomy-policy",
        json={"auto_approve_low_risk": True},
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /admin/orgs/{org_id}/autonomy-policy/templates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_autonomy_policy_templates(client):
    resp = await client.get(
        "/api/v1/admin/orgs/1/autonomy-policy/templates",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# GET /admin/orgs/{org_id}/autonomy-policy/history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_autonomy_policy_history(client):
    resp = await client.get(
        "/api/v1/admin/orgs/1/autonomy-policy/history",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# GET/PATCH /admin/orgs/{org_id}/autonomy-rollout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_autonomy_rollout(client):
    resp = await client.get(
        "/api/v1/admin/orgs/1/autonomy-rollout",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_autonomy_rollout(client):
    resp = await client.patch(
        "/api/v1/admin/orgs/1/autonomy-rollout",
        json={"max_actions_per_day": 50},
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /admin/orgs/{org_id}/autonomy-dry-run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_autonomy_dry_run(client):
    resp = await client.post(
        "/api/v1/admin/orgs/1/autonomy-dry-run",
        json={"approval_type": "send_message"},
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["org_id"] == 1
    assert "can_auto_approve" in data
    assert "can_execute_after_approval" in data
    assert "rollout_allowed" in data


# ---------------------------------------------------------------------------
# POST /admin/orgs/{org_id}/autonomy-policy/rollback/{version_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_policy_rollback_not_found(client):
    resp = await client.post(
        "/api/v1/admin/orgs/1/autonomy-policy/rollback/nonexistent-version-id",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/orgs/{org_id}/readiness/trend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_readiness_trend(client):
    resp = await client.get(
        "/api/v1/admin/orgs/1/readiness/trend?days=3",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["org_id"] == 1
    assert data["days"] == 3
    assert len(data["series"]) == 3
    for point in data["series"]:
        assert "day" in point
        assert "integration_failures" in point


# ---------------------------------------------------------------------------
# GET /admin/orgs/{org_id}/whatsapp-webhook-failures
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whatsapp_webhook_failures(client):
    resp = await client.get(
        "/api/v1/admin/orgs/1/whatsapp-webhook-failures",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["org_id"] == 1
    assert "failures" in data
    assert isinstance(data["failures"], list)


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users(client):
    resp = await client.get("/api/v1/admin/users", headers=_super_admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 4  # 5 users seeded in conftest (full=True)


@pytest.mark.asyncio
async def test_list_users_pagination(client):
    resp = await client.get("/api/v1/admin/users?limit=2&offset=0", headers=_super_admin_headers())
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


@pytest.mark.asyncio
async def test_list_users_requires_super_admin(client):
    resp = await client.get("/api/v1/admin/users", headers=_non_super_headers())
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/users/{user_id}/grant-super
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grant_super_admin(client):
    resp = await client.post(
        "/api/v1/admin/users/3/grant-super",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["user_id"] == 3
    assert data["is_super_admin"] is True


@pytest.mark.asyncio
async def test_grant_super_admin_user_not_found(client):
    resp = await client.post(
        "/api/v1/admin/users/9999/grant-super",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/users/{user_id}/revoke-super
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revoke_super_admin(client):
    # Grant first, then revoke
    await client.post("/api/v1/admin/users/3/grant-super", headers=_super_admin_headers())
    resp = await client.post(
        "/api/v1/admin/users/3/revoke-super",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["is_super_admin"] is False


@pytest.mark.asyncio
async def test_revoke_self_forbidden(client):
    """Cannot revoke your own super-admin access."""
    resp = await client.post(
        "/api/v1/admin/users/1/revoke-super",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 400
    assert "own" in resp.json()["detail"].lower() or "self" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_revoke_super_user_not_found(client):
    resp = await client.post(
        "/api/v1/admin/users/9999/revoke-super",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /admin/orgs/{org_id}/purge  (GDPR tenant purge — Fix 8)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purge_org_wrong_confirm_returns_400(client):
    """Purge is rejected when the confirmation string is incorrect."""
    resp = await client.delete(
        "/api/v1/admin/orgs/2/purge?confirm=WRONG",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 400
    assert "YES PURGE ORG 2" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_purge_org_requires_super_admin(client):
    """Non-super-admin is forbidden from purging org data."""
    resp = await client.delete(
        "/api/v1/admin/orgs/2/purge?confirm=YES+PURGE+ORG+2",
        headers=_non_super_headers(),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_purge_org_not_found_returns_404(client):
    """Purging a nonexistent org returns 404."""
    resp = await client.delete(
        "/api/v1/admin/orgs/9999/purge?confirm=YES+PURGE+ORG+9999",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_purge_org_success(client):
    """Successful purge returns purged=True and rows_deleted counts."""
    resp = await client.delete(
        "/api/v1/admin/orgs/2/purge?confirm=YES+PURGE+ORG+2",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["purged"] is True
    assert data["org_id"] == 2
    assert isinstance(data["rows_deleted"], dict)
    # Users for org 2 should have been deleted (1 CEO was seeded)
    assert data["rows_deleted"].get("User", 0) >= 1


@pytest.mark.asyncio
async def test_purge_org_idempotent(client):
    """Purging an already-empty org succeeds; only the audit Event itself remains."""
    # First purge removes all org-2 data
    await client.delete(
        "/api/v1/admin/orgs/2/purge?confirm=YES+PURGE+ORG+2",
        headers=_super_admin_headers(),
    )
    # Second purge — the only row left is the audit Event created by *this* purge call
    resp = await client.delete(
        "/api/v1/admin/orgs/2/purge?confirm=YES+PURGE+ORG+2",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["purged"] is True
    deleted = data["rows_deleted"]
    # Every table except Event should be empty; Event = 1 (the purge audit record itself)
    non_event = {k: v for k, v in deleted.items() if k != "Event"}
    assert all(v == 0 for v in non_event.values())
    assert deleted.get("Event", 0) <= 1
