from app.core.security import create_access_token


async def test_error_envelope_forbidden_includes_code_and_request_id(client):
    staff = create_access_token({"id": 2, "email": "staff@org.com", "role": "STAFF", "org_id": 1})
    response = await client.get(
        "/api/v1/memory/profile",
        headers={"Authorization": f"Bearer {staff}"},
    )
    body = response.json()
    assert response.status_code == 403
    assert body["code"] == "forbidden"
    assert isinstance(body["detail"], str)
    assert "request_id" in body
    assert "contract_version" in body


async def test_error_envelope_validation_includes_code_and_request_id(client):
    response = await client.get("/api/v1/ops/events?limit=0")
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert isinstance(body["detail"], list)
    assert "request_id" in body
    assert "contract_version" in body


async def test_contract_header_present_on_success(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers.get("X-API-Contract-Version")
