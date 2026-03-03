"""Basic smoke tests for super-admin API routes."""

from tests.conftest import _make_auth_headers


async def test_admin_orgs_requires_super_admin(client):
    # normal CEO (id=1) is super-admin via seed; ensure works
    resp = await client.get("/api/v1/admin/orgs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # non-super user id=2 should be forbidden
    headers = _make_auth_headers(user_id=2, email="ceo@org2.com", role="CEO", org_id=2)
    resp2 = await client.get("/api/v1/admin/orgs", headers=headers)
    assert resp2.status_code == 403
    assert "Super-admin" in resp2.json()["detail"]
