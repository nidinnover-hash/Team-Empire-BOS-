from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.user import User
from tests.conftest import _make_auth_headers


async def _get_test_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


@pytest.mark.asyncio
async def test_auth_rejects_unknown_user(client):
    headers = _make_auth_headers(9999, "unknown@org1.com", "CEO", 1)
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_rejects_org_mismatch(client):
    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 2)
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_rejects_token_version_mismatch(client):
    session, agen = await _get_test_session()
    try:
        user = (await session.execute(select(User).where(User.id == 1))).scalar_one()
        user.token_version = 2
        session.add(user)
        await session.commit()
    finally:
        await agen.aclose()

    headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_role_check_returns_403_for_authenticated_but_unauthorized_user(client):
    create_resp = await client.post(
        "/api/v1/users",
        json={
            "organization_id": 1,
            "name": "Role Matrix User",
            "email": "role-matrix-user@org1.com",
            "password": "TestPass123!",
            "role": "STAFF",
        },
        headers=_make_auth_headers(1, "ceo@org1.com", "CEO", 1),
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    unauthorized = await client.patch(
        f"/api/v1/users/{user_id}/role",
        json={"role": "MANAGER"},
        headers=_make_auth_headers(3, "manager@org1.com", "MANAGER", 1),
    )
    assert unauthorized.status_code == 403


@pytest.mark.asyncio
async def test_email_claim_mismatch_does_not_downgrade_to_401(client):
    create_resp = await client.post(
        "/api/v1/users",
        json={
            "organization_id": 1,
            "name": "Email Claim Matrix User",
            "email": "email-claim-matrix@org1.com",
            "password": "TestPass123!",
            "role": "STAFF",
        },
        headers=_make_auth_headers(1, "ceo@org1.com", "CEO", 1),
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    # User id/org/token_version are valid; only email claim is stale/incorrect.
    # Contract: authentication remains valid and RBAC returns 403 for this route.
    stale_email_headers = _make_auth_headers(3, "stale-manager-email@org1.com", "MANAGER", 1)
    unauthorized = await client.patch(
        f"/api/v1/users/{user_id}/role",
        json={"role": "MANAGER"},
        headers=stale_email_headers,
    )
    assert unauthorized.status_code == 403
