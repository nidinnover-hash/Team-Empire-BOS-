"""
Tests that Literal-validated schema fields properly reject invalid values.
These verify MED-8 (unvalidated enum strings) is fixed.
"""
from datetime import date

TODAY = str(date.today())


# ── Finance type: only "income" or "expense" ─────────────────────────────────

async def test_finance_invalid_type_rejected(client):
    response = await client.post(
        "/api/v1/finance",
        json={"type": "donation", "amount": 100.0, "category": "other", "entry_date": TODAY},
    )
    assert response.status_code == 422


async def test_finance_valid_income_accepted(client):
    response = await client.post(
        "/api/v1/finance",
        json={"type": "income", "amount": 500.0, "category": "salary", "entry_date": TODAY},
    )
    assert response.status_code == 201


async def test_finance_valid_expense_accepted(client):
    response = await client.post(
        "/api/v1/finance",
        json={"type": "expense", "amount": 50.0, "category": "food", "entry_date": TODAY},
    )
    assert response.status_code == 201


# ── Project status: only "active|completed|paused|archived" ──────────────────

async def test_project_invalid_status_rejected(client):
    pid = (await client.post("/api/v1/projects", json={"title": "P"})).json()["id"]
    response = await client.patch(
        f"/api/v1/projects/{pid}/status",
        json={"status": "deleted"},
    )
    assert response.status_code == 422


async def test_project_valid_statuses_accepted(client):
    for status in ("active", "completed", "paused", "archived"):
        pid = (await client.post("/api/v1/projects", json={"title": f"P-{status}"})).json()["id"]
        resp = await client.patch(f"/api/v1/projects/{pid}/status", json={"status": status})
        assert resp.status_code == 200, f"status={status} should be accepted"


# ── Goal status: only "active|completed|paused|abandoned" ────────────────────

async def test_goal_invalid_status_rejected(client):
    gid = (await client.post("/api/v1/goals", json={"title": "G"})).json()["id"]
    response = await client.patch(
        f"/api/v1/goals/{gid}/status",
        json={"status": "retired"},
    )
    assert response.status_code == 422


async def test_goal_valid_statuses_accepted(client):
    for status in ("active", "completed", "paused", "abandoned"):
        gid = (await client.post("/api/v1/goals", json={"title": f"G-{status}"})).json()["id"]
        resp = await client.patch(f"/api/v1/goals/{gid}/status", json={"status": status})
        assert resp.status_code == 200, f"status={status} should be accepted"


# ── Contact relationship: only "personal|business|family|mentor|other" ───────

async def test_contact_invalid_relationship_rejected(client):
    response = await client.post(
        "/api/v1/contacts",
        json={"name": "Test", "relationship": "acquaintance"},
    )
    assert response.status_code == 422


async def test_contact_valid_relationships_accepted(client):
    for rel in ("personal", "business", "family", "mentor", "other"):
        resp = await client.post(
            "/api/v1/contacts",
            json={"name": f"Contact-{rel}", "relationship": rel},
        )
        assert resp.status_code == 201, f"relationship={rel} should be accepted"


# ── Security headers ──────────────────────────────────────────────────────────

async def test_security_headers_present(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "x-xss-protection" in response.headers
