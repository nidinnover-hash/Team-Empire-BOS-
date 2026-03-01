"""Tests for API key management (CRUD, validation, isolation)."""

from __future__ import annotations

import pytest

from tests.conftest import _make_auth_headers

CEO_HEADERS = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
ORG2_HEADERS = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)
STAFF_HEADERS = _make_auth_headers(4, "staff@org1.com", "STAFF", 1)

BASE = "/api/v1/api-keys"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_key(client, name="Test Key", scopes="*", headers=None):
    return await client.post(
        BASE,
        json={"name": name, "scopes": scopes},
        headers=headers or CEO_HEADERS,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_api_key(client):
    resp = await _create_key(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Key"
    assert data["key"].startswith("nbos_")
    assert data["key_prefix"] == data["key"][:12]
    assert data["scopes"] == "*"


@pytest.mark.asyncio
async def test_list_api_keys(client):
    await _create_key(client, name="Key A")
    await _create_key(client, name="Key B")
    resp = await client.get(BASE, headers=CEO_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 2
    names = [k["name"] for k in data["items"]]
    assert "Key A" in names
    assert "Key B" in names


@pytest.mark.asyncio
async def test_revoke_api_key(client):
    create_resp = await _create_key(client)
    key_id = create_resp.json()["id"]
    resp = await client.delete(f"{BASE}/{key_id}", headers=CEO_HEADERS)
    assert resp.status_code == 204

    # Verify it shows as revoked
    list_resp = await client.get(BASE, headers=CEO_HEADERS)
    revoked = [k for k in list_resp.json()["items"] if k["id"] == key_id]
    assert len(revoked) == 1
    assert revoked[0]["is_active"] is False


@pytest.mark.asyncio
async def test_revoke_nonexistent_key(client):
    resp = await client.delete(f"{BASE}/99999", headers=CEO_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_isolation(client):
    """Keys from org1 should not be visible to org2."""
    await _create_key(client, name="Org1 Key", headers=CEO_HEADERS)
    resp = await client.get(BASE, headers=ORG2_HEADERS)
    assert resp.status_code == 200
    names = [k["name"] for k in resp.json()["items"]]
    assert "Org1 Key" not in names


@pytest.mark.asyncio
async def test_staff_cannot_create(client):
    resp = await _create_key(client, headers=STAFF_HEADERS)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_with_expiry(client):
    resp = await client.post(
        BASE,
        json={"name": "Expiring Key", "scopes": "*", "expires_in_days": 30},
        headers=CEO_HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["expires_at"] is not None


@pytest.mark.asyncio
async def test_key_not_shown_in_list(client):
    """Full key should only be in create response, not list."""
    create_resp = await _create_key(client)
    full_key = create_resp.json()["key"]
    list_resp = await client.get(BASE, headers=CEO_HEADERS)
    for k in list_resp.json()["items"]:
        assert "key" not in k or k.get("key") != full_key


# ---------------------------------------------------------------------------
# Service-level validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_api_key_service(db):
    from app.services import api_key as api_key_service

    api_key, full_key = await api_key_service.create_api_key(
        db, organization_id=1, user_id=1, name="Validate Test",
    )
    result = await api_key_service.validate_api_key(db, full_key)
    assert result is not None
    assert result.id == api_key.id


@pytest.mark.asyncio
async def test_validate_invalid_key(db):
    from app.services import api_key as api_key_service

    result = await api_key_service.validate_api_key(db, "nbos_invalid_key_value")
    assert result is None


@pytest.mark.asyncio
async def test_validate_revoked_key(db):
    from app.services import api_key as api_key_service

    api_key, full_key = await api_key_service.create_api_key(
        db, organization_id=1, user_id=1, name="Revoke Test",
    )
    await api_key_service.revoke_api_key(db, api_key.id, organization_id=1, user_id=1)
    result = await api_key_service.validate_api_key(db, full_key)
    assert result is None


@pytest.mark.asyncio
async def test_api_key_can_access_read_endpoint(client):
    create_resp = await _create_key(client, scopes="read")
    full_key = create_resp.json()["key"]
    headers = {"Authorization": f"Bearer {full_key}"}
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "ceo@org1.com"


@pytest.mark.asyncio
async def test_api_key_read_scope_cannot_write(client):
    create_resp = await _create_key(client, scopes="read")
    full_key = create_resp.json()["key"]
    headers = {"Authorization": f"Bearer {full_key}"}
    resp = await client.post(
        BASE,
        json={"name": "Blocked Write", "scopes": "read"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "required permissions" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_key_resource_scope_allows_matching_read(client):
    create_resp = await _create_key(client, scopes="webhooks:read")
    full_key = create_resp.json()["key"]
    headers = {"Authorization": f"Bearer {full_key}"}
    resp = await client.get("/api/v1/webhooks", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_key_resource_scope_blocks_other_resources(client):
    create_resp = await _create_key(client, scopes="webhooks:read")
    full_key = create_resp.json()["key"]
    headers = {"Authorization": f"Bearer {full_key}"}
    resp = await client.get("/api/v1/integrations", headers=headers)
    assert resp.status_code == 403
    assert "required permissions" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_key_resource_write_scope_allows_matching_write(client):
    create_resp = await _create_key(client, scopes="api_keys:write")
    full_key = create_resp.json()["key"]
    headers = {"Authorization": f"Bearer {full_key}"}
    resp = await client.post(
        BASE,
        json={"name": "Resource Writer", "scopes": "api_keys:read"},
        headers=headers,
    )
    assert resp.status_code == 201
