from datetime import UTC, datetime

from sqlalchemy import select

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.integration import Integration
from app.services import integration as integration_service


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


async def test_generic_connect_blocks_provider_specific_types(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    blocked = await client.post(
        "/api/v1/integrations/connect",
        json={"type": "github", "config_json": {"access_token": "ghp_x"}},
        headers=headers,
    )
    assert blocked.status_code == 400
    assert "provider-specific verification endpoint" in blocked.json()["detail"]


async def test_decrypted_read_does_not_persist_plaintext_tokens_on_commit(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "gmail",
            "config_json": {"access_token": "ghp_sensitive_token_123"},
        },
        headers=headers,
    )
    assert connected.status_code == 201
    integration_id = connected.json()["id"]

    override = fastapi_app.dependency_overrides[get_db]

    # Read via service (decrypted), then commit unrelated field update.
    agen = override()
    session = await agen.__anext__()
    try:
        item = await integration_service.get_integration_by_type(session, 1, "gmail")
        assert item is not None
        assert item.config_json.get("access_token") == "ghp_sensitive_token_123"
        item.updated_at = datetime.now(UTC)
        await session.commit()
    finally:
        await agen.aclose()

    # Raw DB row must still hold encrypted token ciphertext.
    agen2 = override()
    session2 = await agen2.__anext__()
    try:
        result = await session2.execute(select(Integration).where(Integration.id == integration_id))
        raw = result.scalar_one()
        token = raw.config_json.get("access_token", "")
        assert isinstance(token, str)
        assert token.startswith("gAAAA")
    finally:
        await agen2.aclose()
