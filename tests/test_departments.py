"""Tests for department CRUD endpoints."""

import pytest


@pytest.mark.asyncio
async def test_create_department(client):
    resp = await client.post("/api/v1/departments", json={
        "name": "Engineering", "code": "ENG",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Engineering"
    assert data["code"] == "ENG"
    assert data["is_active"] is True
    assert data["organization_id"] == 1


@pytest.mark.asyncio
async def test_list_departments(client):
    await client.post("/api/v1/departments", json={"name": "Sales", "code": "SALES"})
    await client.post("/api/v1/departments", json={"name": "HR", "code": "HR"})

    resp = await client.get("/api/v1/departments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    names = [d["name"] for d in data]
    assert "Sales" in names
    assert "HR" in names


@pytest.mark.asyncio
async def test_get_department(client):
    create = await client.post("/api/v1/departments", json={"name": "Marketing", "code": "MKT"})
    dept_id = create.json()["id"]

    resp = await client.get(f"/api/v1/departments/{dept_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Marketing"


@pytest.mark.asyncio
async def test_get_department_not_found(client):
    resp = await client.get("/api/v1/departments/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_department(client):
    create = await client.post("/api/v1/departments", json={"name": "Ops", "code": "OPS"})
    dept_id = create.json()["id"]

    resp = await client.patch(f"/api/v1/departments/{dept_id}", json={"name": "Operations"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Operations"


@pytest.mark.asyncio
async def test_deactivate_department(client):
    create = await client.post("/api/v1/departments", json={"name": "Temp", "code": "TMP"})
    dept_id = create.json()["id"]

    resp = await client.delete(f"/api/v1/departments/{dept_id}")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_create_department_with_parent(client):
    parent = await client.post("/api/v1/departments", json={"name": "Tech", "code": "TECH"})
    parent_id = parent.json()["id"]

    child = await client.post("/api/v1/departments", json={
        "name": "Frontend", "code": "FE", "parent_department_id": parent_id,
    })
    assert child.status_code == 201
    assert child.json()["parent_department_id"] == parent_id


@pytest.mark.asyncio
async def test_list_departments_active_only(client):
    await client.post("/api/v1/departments", json={"name": "Active Dept", "code": "ACT"})
    deact = await client.post("/api/v1/departments", json={"name": "Inactive Dept", "code": "INA"})
    await client.delete(f"/api/v1/departments/{deact.json()['id']}")

    resp = await client.get("/api/v1/departments?active_only=true")
    names = [d["name"] for d in resp.json()]
    assert "Active Dept" in names
    assert "Inactive Dept" not in names
