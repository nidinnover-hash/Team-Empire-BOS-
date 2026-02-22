from app.core.security import create_access_token


def _auth_headers(user_id: int, email: str, role: str, org_id: int) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def test_connect_and_list_integrations(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "google_calendar",
            "config_json": {"access_token": "token-123"},
        },
        headers=headers,
    )
    assert connected.status_code == 201
    assert connected.json()["type"] == "google_calendar"

    listed = await client.get("/api/v1/integrations", headers=headers)
    assert listed.status_code == 200
    assert any(item["type"] == "google_calendar" for item in listed.json())


async def test_test_integration_reports_config_failure(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={"type": "google_calendar", "config_json": {}},
        headers=headers,
    )
    assert connected.status_code == 201
    integration_id = connected.json()["id"]

    tested = await client.post(
        f"/api/v1/integrations/{integration_id}/test",
        headers=headers,
    )
    assert tested.status_code == 200
    assert tested.json()["status"] == "failed"


async def test_cross_org_disconnect_is_denied_by_not_found(client):
    org1_headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "gmail",
            "config_json": {"access_token": "x"},
        },
        headers=org1_headers,
    )
    assert connected.status_code == 201
    integration_id = connected.json()["id"]

    org2_headers = _auth_headers(2, "ceo@org2.com", "CEO", 2)
    response = await client.post(
        f"/api/v1/integrations/{integration_id}/disconnect",
        headers=org2_headers,
    )
    assert response.status_code == 404
