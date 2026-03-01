"""Tests for enhanced employee CRUD (department_id, employment_status)."""

import pytest


@pytest.mark.asyncio
async def test_create_employee_with_department(client):
    dept = await client.post("/api/v1/departments", json={"name": "Dev", "code": "DEV"})
    dept_id = dept.json()["id"]

    resp = await client.post("/api/v1/ops/employees", json={
        "name": "Alice", "email": "alice@example.com", "role": "Developer",
        "department_id": dept_id, "employment_status": "active",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["department_id"] == dept_id
    assert data["employment_status"] == "active"


@pytest.mark.asyncio
async def test_update_employee_department(client):
    dept1 = await client.post("/api/v1/departments", json={"name": "D1", "code": "D1"})
    dept2 = await client.post("/api/v1/departments", json={"name": "D2", "code": "D2"})

    emp = await client.post("/api/v1/ops/employees", json={
        "name": "Bob", "email": "bob@example.com", "department_id": dept1.json()["id"],
    })
    emp_id = emp.json()["id"]

    resp = await client.patch(f"/api/v1/ops/employees/{emp_id}", json={
        "department_id": dept2.json()["id"],
    })
    assert resp.status_code == 200
    assert resp.json()["department_id"] == dept2.json()["id"]


@pytest.mark.asyncio
async def test_create_employee_default_status(client):
    resp = await client.post("/api/v1/ops/employees", json={
        "name": "Charlie", "email": "charlie@example.com",
    })
    assert resp.status_code == 201
    assert resp.json()["employment_status"] == "active"


@pytest.mark.asyncio
async def test_list_employees_basic(client):
    await client.post("/api/v1/ops/employees", json={
        "name": "Dave", "email": "dave@example.com",
    })
    resp = await client.get("/api/v1/ops/employees")
    assert resp.status_code == 200
    assert any(e["name"] == "Dave" for e in resp.json())


@pytest.mark.asyncio
async def test_update_employment_status(client):
    emp = await client.post("/api/v1/ops/employees", json={
        "name": "Eve", "email": "eve@example.com",
    })
    emp_id = emp.json()["id"]

    resp = await client.patch(f"/api/v1/ops/employees/{emp_id}", json={
        "employment_status": "on_leave",
    })
    assert resp.status_code == 200
    assert resp.json()["employment_status"] == "on_leave"
