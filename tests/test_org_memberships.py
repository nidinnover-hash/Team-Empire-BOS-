from app.core.security import create_access_token


def _auth_headers(user_id: int, email: str, role: str, org_id: int) -> dict[str, str]:
    token = create_access_token({"id": user_id, "email": email, "role": role, "org_id": org_id})
    return {"Authorization": f"Bearer {token}"}


async def test_org_membership_upsert_and_list(client):
    ceo_headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    user_resp = await client.post(
        "/api/v1/users",
        json={
            "name": "Org Member",
            "email": "member@org.com",
            "password": "SecurePass123!",
            "role": "STAFF",
            "organization_id": 1,
        },
        headers=ceo_headers,
    )
    assert user_resp.status_code == 201
    user_id = user_resp.json()["id"]

    upsert_resp = await client.post(
        "/api/v1/orgs/1/members",
        json={"user_id": user_id, "role": "TECH_LEAD"},
        headers=ceo_headers,
    )
    assert upsert_resp.status_code == 201
    assert upsert_resp.json()["role"] == "TECH_LEAD"

    list_resp = await client.get("/api/v1/orgs/1/members", headers=ceo_headers)
    assert list_resp.status_code == 200
    assert any(item["user_id"] == user_id for item in list_resp.json())
