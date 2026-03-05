"""Tests for employee mapping endpoints (POST + GET /api/v1/ops/employees)."""
from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.organization import Organization
from tests.conftest import _make_auth_headers


async def _seed_org(org_id: int = 1) -> None:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        if await session.get(Organization, org_id) is None:
            session.add(Organization(id=org_id, name=f"Org {org_id}", slug=f"org-{org_id}"))
            await session.commit()
    finally:
        await agen.aclose()


async def test_create_employee(client):
    await _seed_org()
    response = await client.post(
        "/api/v1/ops/employees",
        json={"name": "Alice", "email": "alice@test.com", "job_title": "Developer"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alice"
    assert body["email"] == "alice@test.com"
    assert body["job_title"] == "Developer"
    assert body["is_active"] is True
    assert body["organization_id"] == 1
    assert "id" in body


async def test_create_employee_upserts_on_same_email(client):
    await _seed_org()
    await client.post(
        "/api/v1/ops/employees",
        json={"name": "Alice V1", "email": "alice@test.com", "job_title": "Junior"},
    )
    response = await client.post(
        "/api/v1/ops/employees",
        json={"name": "Alice V2", "email": "alice@test.com", "job_title": "Senior"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alice V2"
    assert body["job_title"] == "Senior"

    # Only one employee should exist
    list_resp = await client.get("/api/v1/ops/employees")
    assert len(list_resp.json()) == 1


async def test_list_employees_active_only(client):
    await _seed_org()
    await client.post("/api/v1/ops/employees", json={"name": "Active", "email": "a@t.com"})
    await client.post("/api/v1/ops/employees", json={"name": "Inactive", "email": "b@t.com", "is_active": False})

    resp = await client.get("/api/v1/ops/employees")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Active"

    resp_all = await client.get("/api/v1/ops/employees?active_only=false")
    assert len(resp_all.json()) == 2


async def test_get_employee_by_id(client):
    await _seed_org()
    create_resp = await client.post(
        "/api/v1/ops/employees",
        json={"name": "Bob", "email": "bob@test.com"},
    )
    emp_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/ops/employees/{emp_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Bob"


async def test_get_employee_not_found(client):
    resp = await client.get("/api/v1/ops/employees/999")
    assert resp.status_code == 404


async def test_update_employee(client):
    await _seed_org()
    create_resp = await client.post(
        "/api/v1/ops/employees",
        json={"name": "Charlie", "email": "charlie@test.com"},
    )
    emp_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/ops/employees/{emp_id}",
        json={"github_username": "charlie-gh", "job_title": "Lead"},
    )
    assert resp.status_code == 200
    assert resp.json()["github_username"] == "charlie-gh"
    assert resp.json()["job_title"] == "Lead"
    assert resp.json()["name"] == "Charlie"  # unchanged


async def test_employee_cross_org_isolation(client):
    """Employee created by org 1 is not visible to org 2."""
    await _seed_org(1)
    await _seed_org(2)

    # Create as org 1
    await client.post(
        "/api/v1/ops/employees",
        json={"name": "Org1 Employee", "email": "emp@org1.com"},
        headers=_make_auth_headers(org_id=1),
    )

    # List as org 2
    resp = await client.get(
        "/api/v1/ops/employees",
        headers=_make_auth_headers(user_id=2, email="ceo@org2.com", org_id=2),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


async def test_employee_requires_admin_role(client):
    """STAFF cannot access employee endpoints."""
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF")
    resp = await client.get("/api/v1/ops/employees", headers=staff_headers)
    assert resp.status_code == 403


async def test_create_employee_with_integration_ids(client):
    await _seed_org()
    resp = await client.post(
        "/api/v1/ops/employees",
        json={
            "name": "Dave",
            "email": "dave@test.com",
            "github_username": "dave-gh",
            "clickup_user_id": "cu_12345",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["github_username"] == "dave-gh"
    assert body["clickup_user_id"] == "cu_12345"
