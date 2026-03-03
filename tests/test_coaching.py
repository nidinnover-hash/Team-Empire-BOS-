"""Tests for the dedicated coaching endpoints."""

import pytest


async def _create_employee(client, name: str, email: str) -> int:
    resp = await client.post("/api/v1/ops/employees", json={"name": name, "email": email})
    assert resp.status_code in (200, 201)
    return resp.json()["id"]


# ── Generation endpoints ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_employee_coaching(client):
    emp_id = await _create_employee(client, "Coach Target", "coach@bos.test")
    resp = await client.post(f"/api/v1/coaching/employee/{emp_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data
    assert data["status"] == "pending"
    assert "recommendations" in data


@pytest.mark.asyncio
async def test_generate_employee_coaching_not_found(client):
    resp = await client.post("/api/v1/coaching/employee/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_org_improvement_plan(client):
    resp = await client.post("/api/v1/coaching/org")
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data
    assert data["status"] == "pending"


# ── Report management endpoints ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_coaching_reports_empty(client):
    resp = await client.get("/api/v1/coaching")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_coaching_reports_after_generation(client):
    emp_id = await _create_employee(client, "List Target", "list@bos.test")
    await client.post(f"/api/v1/coaching/employee/{emp_id}")

    resp = await client.get("/api/v1/coaching")
    assert resp.status_code == 200
    reports = resp.json()
    assert len(reports) >= 1
    assert reports[0]["report_type"] == "employee"
    assert reports[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_coaching_report(client):
    emp_id = await _create_employee(client, "Get Target", "get@bos.test")
    gen = await client.post(f"/api/v1/coaching/employee/{emp_id}")
    report_id = gen.json()["report_id"]

    resp = await client.get(f"/api/v1/coaching/{report_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == report_id
    assert "recommendations" in data


@pytest.mark.asyncio
async def test_get_coaching_report_not_found(client):
    resp = await client.get("/api/v1/coaching/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_coaching_report(client):
    emp_id = await _create_employee(client, "Approve Target", "approve@bos.test")
    gen = await client.post(f"/api/v1/coaching/employee/{emp_id}")
    report_id = gen.json()["report_id"]

    resp = await client.patch(f"/api/v1/coaching/{report_id}/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["approved_by"] is not None


@pytest.mark.asyncio
async def test_reject_coaching_report(client):
    emp_id = await _create_employee(client, "Reject Target", "reject@bos.test")
    gen = await client.post(f"/api/v1/coaching/employee/{emp_id}")
    report_id = gen.json()["report_id"]

    resp = await client.patch(f"/api/v1/coaching/{report_id}/reject?note=Not+applicable")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"


# ── Learning insights ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_learning_insights(client):
    resp = await client.get("/api/v1/coaching/insights?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_reports" in data
    assert "effectiveness" in data


# ── Pending-report rate limit (Fix 9) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_pending_report_limit_blocks_at_cap(client):
    """After _MAX_PENDING_REPORTS pending reports the next generation returns 429."""
    from app.api.v1.endpoints.coaching import _MAX_PENDING_REPORTS

    # Fill the queue using org-level reports (no employee setup needed)
    for i in range(_MAX_PENDING_REPORTS):
        resp = await client.post("/api/v1/coaching/org")
        assert resp.status_code == 200, (
            f"Expected 200 on attempt {i + 1}, got {resp.status_code}: {resp.text}"
        )

    # The next call must be blocked
    resp = await client.post("/api/v1/coaching/org")
    assert resp.status_code == 429
    detail = resp.json()["detail"]
    assert str(_MAX_PENDING_REPORTS) in detail
    assert "pending" in detail.lower()


@pytest.mark.asyncio
async def test_pending_report_limit_resets_after_approval(client):
    """Approving a pending report frees a slot so generation succeeds again."""
    from app.api.v1.endpoints.coaching import _MAX_PENDING_REPORTS

    # Fill to cap
    report_ids = []
    for _ in range(_MAX_PENDING_REPORTS):
        r = await client.post("/api/v1/coaching/org")
        assert r.status_code == 200
        report_ids.append(r.json()["report_id"])

    # Confirm cap is hit
    assert (await client.post("/api/v1/coaching/org")).status_code == 429

    # Approve one report to free a slot
    approve_resp = await client.patch(f"/api/v1/coaching/{report_ids[0]}/approve")
    assert approve_resp.status_code == 200

    # Now generation should succeed again
    resp = await client.post("/api/v1/coaching/org")
    assert resp.status_code == 200
