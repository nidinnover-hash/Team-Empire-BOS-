"""Tests for super-admin cross-org analytics layer."""
import pytest

from app.core.security import create_access_token


def _super_token() -> dict:
    """Token for user id=1 (ceo@org1.com) who is seeded as is_super_admin=True."""
    token = create_access_token({
        "id": 1, "email": "ceo@org1.com", "role": "CEO",
        "org_id": 1, "token_version": 1,
    })
    return {"Authorization": f"Bearer {token}"}


def _regular_token() -> dict:
    """Token for user id=2 (ceo@org2.com) who is NOT super-admin."""
    token = create_access_token({
        "id": 2, "email": "ceo@org2.com", "role": "CEO",
        "org_id": 2, "token_version": 1,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_regular_ceo_cannot_access_admin_orgs(client):
    r = await client.get("/api/v1/admin/orgs", headers=_regular_token())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_list_orgs(client):
    r = await client.get("/api/v1/admin/orgs", headers=_super_token())
    assert r.status_code == 200
    orgs = r.json()
    assert isinstance(orgs, list)
    assert len(orgs) >= 1
    assert any(o["id"] == 1 for o in orgs)


@pytest.mark.asyncio
async def test_super_admin_can_list_users(client):
    r = await client.get("/api/v1/admin/users", headers=_super_token())
    assert r.status_code == 200
    users = r.json()
    assert isinstance(users, list)
    assert len(users) >= 1


@pytest.mark.asyncio
async def test_grant_super_admin(client):
    # Grant super to user id=3 (manager)
    g = await client.post("/api/v1/admin/users/3/grant-super", headers=_super_token())
    assert g.status_code == 200
    assert g.json()["is_super_admin"] is True


@pytest.mark.asyncio
async def test_revoke_super_admin(client):
    # Grant first, then revoke
    await client.post("/api/v1/admin/users/3/grant-super", headers=_super_token())
    rv = await client.post("/api/v1/admin/users/3/revoke-super", headers=_super_token())
    assert rv.status_code == 200
    assert rv.json()["is_super_admin"] is False


@pytest.mark.asyncio
async def test_cannot_revoke_own_super_admin(client):
    r = await client.post("/api/v1/admin/users/1/revoke-super", headers=_super_token())
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_org_summary_returns_data(client):
    r = await client.get("/api/v1/admin/orgs/1/summary", headers=_super_token())
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert "user_count" in body
    assert "task_count" in body


@pytest.mark.asyncio
async def test_org_summary_404_for_nonexistent(client):
    r = await client.get("/api/v1/admin/orgs/99999/summary", headers=_super_token())
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_regular_ceo_cannot_access_org_readiness(client):
    r = await client.get("/api/v1/admin/orgs/1/readiness", headers=_regular_token())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_org_readiness_returns_score_and_metrics(client):
    r = await client.get("/api/v1/admin/orgs/1/readiness", headers=_super_token())
    assert r.status_code == 200
    body = r.json()
    assert body["org_id"] == 1
    assert body["org_name"] == "Test Org"
    assert isinstance(body["score"], int)
    assert 0 <= body["score"] <= 100
    assert body["status"] in {"ready", "watch", "blocked"}
    assert isinstance(body["blockers"], list)
    assert isinstance(body["recommendations"], list)
    assert isinstance(body["metrics"], list)
    assert len(body["metrics"]) >= 5
    assert any(m["name"] == "connected_integrations" for m in body["metrics"])


@pytest.mark.asyncio
async def test_org_readiness_404_for_nonexistent(client):
    r = await client.get("/api/v1/admin/orgs/99999/readiness", headers=_super_token())
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_can_list_fleet_readiness(client):
    r = await client.get("/api/v1/admin/orgs/readiness", headers=_super_token())
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) >= 2
    assert any(item["org_id"] == 1 for item in rows)
    assert any(item["org_id"] == 2 for item in rows)
    assert all("score" in item and "status" in item for item in rows)


@pytest.mark.asyncio
async def test_org_autonomy_gates_returns_modes(client):
    r = await client.get("/api/v1/admin/orgs/1/autonomy-gates", headers=_super_token())
    assert r.status_code == 200
    body = r.json()
    assert body["org_id"] == 1
    assert "suggest_only" in body["allowed_modes"]
    assert isinstance(body["denied_modes"], list)
    assert isinstance(body["reasons"], list)


@pytest.mark.asyncio
async def test_get_org_autonomy_policy_returns_defaults(client):
    r = await client.get("/api/v1/admin/orgs/1/autonomy-policy", headers=_super_token())
    assert r.status_code == 200
    body = r.json()
    assert body["current_mode"] in {"suggest_only", "approved_execution", "autonomous"}
    assert "allow_auto_approval" in body
    assert "min_readiness_for_auto_approval" in body
    assert "updated_at" in body
    assert "updated_by_email" in body


@pytest.mark.asyncio
async def test_patch_org_autonomy_policy_updates_values(client):
    patch_r = await client.patch(
        "/api/v1/admin/orgs/1/autonomy-policy",
        headers=_super_token(),
        json={"current_mode": "suggest_only", "allow_auto_approval": False},
    )
    assert patch_r.status_code == 200
    body = patch_r.json()
    assert body["current_mode"] == "suggest_only"
    assert body["allow_auto_approval"] is False
    assert body["updated_at"] is not None
    assert body["updated_by_email"] == "ceo@org1.com"

    read_r = await client.get("/api/v1/admin/orgs/1/autonomy-policy", headers=_super_token())
    assert read_r.status_code == 200
    assert read_r.json()["current_mode"] == "suggest_only"


@pytest.mark.asyncio
async def test_patch_org_autonomy_policy_writes_audit_event(client):
    patch_r = await client.patch(
        "/api/v1/admin/orgs/1/autonomy-policy",
        headers=_super_token(),
        json={"current_mode": "approved_execution", "allow_auto_approval": True},
    )
    assert patch_r.status_code == 200

    events_r = await client.get(
        "/api/v1/observability/events?event_type=autonomy_policy_updated&days=30",
        headers=_super_token(),
    )
    assert events_r.status_code == 200
    events = events_r.json()
    assert isinstance(events, list)
    assert len(events) >= 1
    payload = events[0]["payload"]
    assert "changed_fields" in payload


@pytest.mark.asyncio
async def test_org_readiness_trend_returns_daily_series(client):
    r = await client.get("/api/v1/admin/orgs/1/readiness/trend?days=5", headers=_super_token())
    assert r.status_code == 200
    body = r.json()
    assert body["org_id"] == 1
    assert body["days"] == 5
    assert isinstance(body["series"], list)
    assert len(body["series"]) == 5
    assert all("day" in point for point in body["series"])
