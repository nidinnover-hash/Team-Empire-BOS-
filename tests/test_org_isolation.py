from typing import cast

from app.core.security import create_access_token
from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.email import Email


def _auth_headers(user_id: int, email: str, role: str, org_id: int) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id, "token_version": 1}
    )
    return {"Authorization": f"Bearer {token}"}


async def _create_second_org(client, headers: dict) -> int:
    response = await client.post(
        "/api/v1/orgs",
        json={"name": "Org Two", "slug": "org-two"},
        headers=headers,
    )
    assert response.status_code == 201
    return cast(int, response.json()["id"])


async def test_orgs_create_and_list(client):
    ceo_headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    org2_id = await _create_second_org(client, ceo_headers)
    assert org2_id >= 1

    # List returns only the actor's own org (org_id=1), not all orgs.
    list_response = await client.get("/api/v1/orgs", headers=ceo_headers)
    assert list_response.status_code == 200
    slugs = {item["slug"] for item in list_response.json()}
    assert "test-org" in slugs
    assert "org-two" not in slugs


async def test_cross_org_project_update_is_denied(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)

    project = await client.post(
        "/api/v1/ops/projects",
        json={"title": "Org1 Private Project"},
        headers=ceo_org1,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    ceo_org2 = _auth_headers(2, "ceo@org2.com", "CEO", 2)
    patch_response = await client.patch(
        f"/api/v1/ops/projects/{project_id}/status",
        json={"status": "paused"},
        headers=ceo_org2,
    )
    assert patch_response.status_code == 404


async def test_cross_org_approval_approve_is_denied(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)

    manager_org1 = _auth_headers(3, "manager@org1.com", "MANAGER", 1)
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "spend", "payload_json": {"amount": 100}},
        headers=manager_org1,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    ceo_org2 = _auth_headers(2, "ceo@org2.com", "CEO", 2)
    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "approve"},
        headers=ceo_org2,
    )
    assert approve.status_code == 404


async def test_cross_org_approval_reject_is_denied(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)

    manager_org1 = _auth_headers(3, "manager@org1.com", "MANAGER", 1)
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "spend", "payload_json": {"amount": 100}},
        headers=manager_org1,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    ceo_org2 = _auth_headers(2, "ceo@org2.com", "CEO", 2)
    reject = await client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"note": "reject"},
        headers=ceo_org2,
    )
    assert reject.status_code == 404


async def test_same_gmail_id_allowed_across_orgs(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)

    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        row1 = Email(
            organization_id=1,
            gmail_id="shared-gmail-id",
            subject="Org1",
        )
        row2 = Email(
            organization_id=2,
            gmail_id="shared-gmail-id",
            subject="Org2",
        )
        session.add(row1)
        session.add(row2)
        await session.commit()
        assert row1.id is not None
        assert row2.id is not None
    finally:
        await agen.aclose()
