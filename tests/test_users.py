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


# ── GET /api/v1/users ────────────────────────────────────────────────────────

async def test_list_users_returns_200_for_ceo(client):
    response = await client.get("/api/v1/users")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_list_users_denied_for_manager(client):
    response = await client.get("/api/v1/users", headers=_auth("MANAGER"))
    assert response.status_code == 403


async def test_list_users_denied_for_staff(client):
    response = await client.get("/api/v1/users", headers=_auth("STAFF"))
    assert response.status_code == 403


# ── POST /api/v1/users ───────────────────────────────────────────────────────

async def test_create_user_returns_201(client):
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Test User",
            "email": "newuser@org.com",
            "password": "SecurePass123!",
            "role": "STAFF",
            "organization_id": 1,
        },
    )
    assert response.status_code == 201


async def test_create_user_returns_correct_fields(client):
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Dev Manager",
            "email": "devmgr@org.com",
            "password": "SecurePass123!",
            "role": "MANAGER",
            "organization_id": 1,
        },
    )
    body = response.json()
    assert body["name"] == "Dev Manager"
    assert body["email"] == "devmgr@org.com"
    assert body["role"] == "MANAGER"
    assert body["is_active"] is True
    assert "id" in body
    assert "created_at" in body
    assert "password" not in body


async def test_create_user_duplicate_email_returns_409(client):
    payload = {
        "name": "First",
        "email": "dupe@org.com",
        "password": "SecurePass123!",
        "role": "STAFF",
        "organization_id": 1,
    }
    await client.post("/api/v1/users", json=payload)
    response = await client.post("/api/v1/users", json=payload)
    assert response.status_code == 409


async def test_create_user_password_too_short_returns_422(client):
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Weak",
            "email": "weak@org.com",
            "password": "short",
            "organization_id": 1,
        },
    )
    assert response.status_code == 422


async def test_create_user_invalid_role_returns_422(client):
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Bad Role",
            "email": "badrole@org.com",
            "password": "SecurePass123!",
            "role": "SUPERADMIN",
            "organization_id": 1,
        },
    )
    assert response.status_code == 422


async def test_create_user_denied_for_manager(client):
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Sneak",
            "email": "sneak@org.com",
            "password": "SecurePass123!",
            "organization_id": 1,
        },
        headers=_auth("MANAGER"),
    )
    assert response.status_code == 403


async def test_create_user_cross_org_denied(client):
    """CEO of org 1 cannot create users for org 2."""
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Cross Org",
            "email": "crossorg@other.com",
            "password": "SecurePass123!",
            "organization_id": 2,
        },
    )
    assert response.status_code == 403
