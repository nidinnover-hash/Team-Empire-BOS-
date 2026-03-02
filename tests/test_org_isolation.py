from typing import cast

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.email import Email
from tests.conftest import _make_auth_headers


async def _create_second_org(client, headers: dict) -> int:
    response = await client.post(
        "/api/v1/orgs",
        json={"name": "Org Two", "slug": "org-two"},
        headers=headers,
    )
    assert response.status_code == 201
    return cast(int, response.json()["id"])


async def test_orgs_create_and_list(client):
    ceo_headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    org2_id = await _create_second_org(client, ceo_headers)
    assert org2_id >= 1

    # List returns only the actor's own org (org_id=1), not all orgs.
    list_response = await client.get("/api/v1/orgs", headers=ceo_headers)
    assert list_response.status_code == 200
    slugs = {item["slug"] for item in list_response.json()}
    assert "test-org" in slugs
    assert "org-two" not in slugs


async def test_org_update_idempotency_replay(client):
    ceo_headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    payload = {"branch_label": "HQ-1"}
    headers = {**ceo_headers, "Idempotency-Key": "org-update-1"}
    first = await client.patch("/api/v1/orgs/1", json=payload, headers=headers)
    assert first.status_code == 200
    second = await client.patch("/api/v1/orgs/1", json=payload, headers=headers)
    assert second.status_code == 200
    assert first.json()["config_version"] == second.json()["config_version"]


async def test_org_feature_flags_concurrency_conflict(client):
    ceo_headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    current = await client.get("/api/v1/orgs/1/feature-flags", headers=ceo_headers)
    assert current.status_code == 200
    v1 = int(current.json()["config_version"])

    ok = await client.patch(
        "/api/v1/orgs/1/feature-flags",
        json={
            "expected_config_version": v1,
            "flags": {
                "trend_snapshots_enabled": {"enabled": True, "rollout_percentage": 100},
            },
        },
        headers=ceo_headers,
    )
    assert ok.status_code == 200

    conflict = await client.patch(
        "/api/v1/orgs/1/feature-flags",
        json={
            "expected_config_version": v1,
            "flags": {
                "trend_snapshots_enabled": {"enabled": False, "rollout_percentage": 0},
            },
        },
        headers=ceo_headers,
    )
    assert conflict.status_code == 409


async def test_cross_org_project_update_is_denied(client):
    ceo_org1 = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)

    project = await client.post(
        "/api/v1/ops/projects",
        json={"title": "Org1 Private Project"},
        headers=ceo_org1,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    ceo_org2 = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)
    patch_response = await client.patch(
        f"/api/v1/ops/projects/{project_id}/status",
        json={"status": "paused"},
        headers=ceo_org2,
    )
    assert patch_response.status_code == 404


async def test_cross_org_approval_approve_is_denied(client):
    ceo_org1 = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)

    manager_org1 = _make_auth_headers(3, "manager@org1.com", "MANAGER", 1)
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "spend", "payload_json": {"amount": 100}},
        headers=manager_org1,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    ceo_org2 = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)
    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "approve"},
        headers=ceo_org2,
    )
    assert approve.status_code == 404


async def test_cross_org_approval_reject_is_denied(client):
    ceo_org1 = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)

    manager_org1 = _make_auth_headers(3, "manager@org1.com", "MANAGER", 1)
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "spend", "payload_json": {"amount": 100}},
        headers=manager_org1,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    ceo_org2 = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)
    reject = await client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"note": "reject"},
        headers=ceo_org2,
    )
    assert reject.status_code == 404


async def test_same_gmail_id_allowed_across_orgs(client):
    ceo_org1 = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
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
