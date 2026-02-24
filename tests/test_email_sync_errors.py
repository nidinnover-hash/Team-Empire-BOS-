from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.integration import Integration
from app.models.organization import Organization
from app.services import email_service


def _auth_headers(user_id: int, email: str, role: str, org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_gmail_integration_for_org1() -> None:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        session.add(Organization(id=1, name="Org 1", slug="org-1"))
        session.add(
            Integration(
                organization_id=1,
                type="gmail",
                config_json={"access_token": "x", "refresh_token": "y"},
                status="connected",
            )
        )
        await session.commit()
    finally:
        await agen.aclose()


async def test_email_sync_returns_502_on_invalid_grant(client, monkeypatch):
    await _seed_gmail_integration_for_org1()

    def fake_fetch_recent_emails(**_kwargs):
        raise RuntimeError("invalid_grant: Bad Request")

    monkeypatch.setattr(email_service.gmail_tool, "fetch_recent_emails", fake_fetch_recent_emails)

    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    response = await client.post("/api/v1/email/sync", headers=headers)

    assert response.status_code == 502
    detail = response.json()["detail"]
    # Error details are now sanitized — no internal codes exposed
    assert "Email sync failed" in detail


async def test_email_health_returns_not_connected_when_missing(client):
    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)
    response = await client.get("/api/v1/email/health", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "not_connected"
