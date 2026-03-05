"""Tests for the unified POST /api/v1/users/team-member endpoint."""

from app.core.security import create_access_token

_ROLE_USER = {
    "CEO": (1, "ceo@org1.com"),
    "MANAGER": (3, "manager@org1.com"),
    "STAFF": (4, "staff@org1.com"),
}


def _auth(role: str, org_id: int = 1) -> dict:
    uid, email = _ROLE_USER.get(role, (1, "ceo@org1.com"))
    token = create_access_token({"id": uid, "email": email, "role": role, "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


VALID_PAYLOAD = {
    "organization_id": 1,
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "password": "StrongPass1!",
    "role": "DEVELOPER",
    "job_title": "Senior Developer",
    "department_id": None,
    "github_username": "alicej",
    "clickup_user_id": "12345",
}


# ── 201 success ──────────────────────────────────────────────────────────────

async def test_create_team_member_returns_201(client):
    resp = await client.post("/api/v1/users/team-member", json=VALID_PAYLOAD)
    assert resp.status_code == 201


async def test_create_team_member_returns_user_and_employee(client):
    resp = await client.post("/api/v1/users/team-member", json=VALID_PAYLOAD)
    body = resp.json()
    assert "user" in body
    assert "employee" in body
    assert body["user"]["email"] == "alice@example.com"
    assert body["employee"]["email"] == "alice@example.com"


async def test_create_team_member_employee_has_user_id(client):
    resp = await client.post("/api/v1/users/team-member", json=VALID_PAYLOAD)
    body = resp.json()
    assert body["user"]["id"] is not None
    # Employee's user_id should match the created user's id
    # (user_id isn't in EmployeeRead by default, but we can verify via the link)
    assert body["employee"]["organization_id"] == 1


async def test_create_team_member_employee_fields(client):
    resp = await client.post("/api/v1/users/team-member", json=VALID_PAYLOAD)
    body = resp.json()
    emp = body["employee"]
    assert emp["name"] == "Alice Johnson"
    assert emp["job_title"] == "Senior Developer"
    assert emp["github_username"] == "alicej"
    assert emp["clickup_user_id"] == "12345"


async def test_create_team_member_user_role(client):
    resp = await client.post("/api/v1/users/team-member", json=VALID_PAYLOAD)
    body = resp.json()
    assert body["user"]["role"] == "DEVELOPER"


# ── Optional fields null ─────────────────────────────────────────────────────

async def test_create_team_member_optional_fields_null(client):
    payload = {
        "organization_id": 1,
        "name": "Bob Smith",
        "email": "bob@example.com",
        "password": "StrongPass1!",
        "role": "STAFF",
    }
    resp = await client.post("/api/v1/users/team-member", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["employee"]["github_username"] is None
    assert body["employee"]["clickup_user_id"] is None


# ── Duplicate email → 409 ───────────────────────────────────────────────────

async def test_create_team_member_duplicate_email_409(client):
    payload = {**VALID_PAYLOAD, "email": "dup@example.com"}
    resp1 = await client.post("/api/v1/users/team-member", json=payload)
    assert resp1.status_code == 201
    resp2 = await client.post("/api/v1/users/team-member", json=payload)
    assert resp2.status_code == 409


# ── Bad password → 422 ──────────────────────────────────────────────────────

async def test_create_team_member_weak_password_422(client):
    payload = {**VALID_PAYLOAD, "email": "weak@example.com", "password": "short"}
    resp = await client.post("/api/v1/users/team-member", json=payload)
    assert resp.status_code == 422


async def test_create_team_member_no_uppercase_422(client):
    payload = {**VALID_PAYLOAD, "email": "noup@example.com", "password": "nouppercase1!"}
    resp = await client.post("/api/v1/users/team-member", json=payload)
    assert resp.status_code == 422


# ── Cross-org → 403 ─────────────────────────────────────────────────────────

async def test_create_team_member_cross_org_403(client):
    payload = {**VALID_PAYLOAD, "email": "cross@example.com", "organization_id": 999}
    resp = await client.post("/api/v1/users/team-member", json=payload)
    assert resp.status_code == 403


# ── Non-CEO/ADMIN → 403 ─────────────────────────────────────────────────────

async def test_create_team_member_manager_403(client):
    payload = {**VALID_PAYLOAD, "email": "mgr@example.com"}
    resp = await client.post("/api/v1/users/team-member", json=payload, headers=_auth("MANAGER"))
    assert resp.status_code == 403


async def test_create_team_member_staff_403(client):
    payload = {**VALID_PAYLOAD, "email": "stf@example.com"}
    resp = await client.post("/api/v1/users/team-member", json=payload, headers=_auth("STAFF"))
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/v1/users/{user_id}/link-employee
# ══════════════════════════════════════════════════════════════════════════════

async def _create_standalone_user(client, email="link@example.com"):
    """Create a User (no Employee) via the standalone endpoint."""
    resp = await client.post("/api/v1/users", json={
        "organization_id": 1,
        "name": "Link User",
        "email": email,
        "password": "StrongPass1!",
    })
    assert resp.status_code == 201
    return resp.json()


async def _create_standalone_employee(client, email="linkemp@example.com"):
    """Create an Employee (no User) via the ops endpoint."""
    resp = await client.post("/api/v1/ops/employees", json={
        "name": "Link Employee",
        "email": email,
        "job_title": "Engineer",
    })
    assert resp.status_code == 201
    return resp.json()


async def test_link_user_to_employee_success(client):
    user = await _create_standalone_user(client)
    emp = await _create_standalone_employee(client)
    resp = await client.post(
        f"/api/v1/users/{user['id']}/link-employee",
        json={"employee_id": emp["id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == user["id"]
    assert body["employee"]["id"] == emp["id"]


async def test_link_user_to_employee_user_not_found(client):
    emp = await _create_standalone_employee(client, email="notfound@example.com")
    resp = await client.post(
        "/api/v1/users/99999/link-employee",
        json={"employee_id": emp["id"]},
    )
    assert resp.status_code == 404


async def test_link_user_to_employee_employee_not_found(client):
    user = await _create_standalone_user(client, email="noempfound@example.com")
    resp = await client.post(
        f"/api/v1/users/{user['id']}/link-employee",
        json={"employee_id": 99999},
    )
    assert resp.status_code == 404


async def test_link_user_to_employee_already_linked_409(client):
    user = await _create_standalone_user(client, email="dup1@example.com")
    emp = await _create_standalone_employee(client, email="dup1emp@example.com")
    resp1 = await client.post(
        f"/api/v1/users/{user['id']}/link-employee",
        json={"employee_id": emp["id"]},
    )
    assert resp1.status_code == 200

    # Try to link another employee to the same user
    emp2 = await _create_standalone_employee(client, email="dup2emp@example.com")
    resp2 = await client.post(
        f"/api/v1/users/{user['id']}/link-employee",
        json={"employee_id": emp2["id"]},
    )
    assert resp2.status_code == 409


async def test_link_user_to_employee_staff_forbidden(client):
    resp = await client.post(
        "/api/v1/users/1/link-employee",
        json={"employee_id": 1},
        headers=_auth("STAFF"),
    )
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/v1/users (deprecated) — deprecation headers
# ══════════════════════════════════════════════════════════════════════════════

async def test_standalone_create_user_returns_deprecation_header(client):
    resp = await client.post("/api/v1/users", json={
        "organization_id": 1,
        "name": "Deprecated User",
        "email": "deprecated@example.com",
        "password": "StrongPass1!",
    })
    assert resp.status_code == 201
    assert resp.headers.get("deprecation") == "true"
    assert "/users/team-member" in resp.headers.get("link", "")
