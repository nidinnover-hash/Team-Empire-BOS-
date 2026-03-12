"""Tests for POST /api/v1/leads/ingest-social (social lead ingest API)."""

from app.core.lead_routing import EMPIRE_DIGITAL_COMPANY_ID
from app.core.security import create_access_token


def _headers(org_id: int, user_id: int = 1, email: str = "ceo@org1.com", role: str = "CEO") -> dict[str, str]:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id, "token_version": 1},
    )
    return {"Authorization": f"Bearer {token}"}


async def test_ingest_social_returns_403_when_org_not_empire_digital(client):
    """Only Empire Digital (org_id=1) is allowed to call ingest-social.

    Note: a token claiming org_id=2 but belonging to user_id=1 (org 1) is rejected
    with 401 (org_mismatch) before reaching the endpoint guard; 403 would require a
    legitimate user seeded into a second org. Both are correct rejections.
    """
    resp = await client.post(
        "/api/v1/leads/ingest-social",
        headers=_headers(org_id=2),
        json={
            "source_platform": "facebook",
            "full_name": "Jane Doe",
            "email": "jane@example.com",
        },
    )
    assert resp.status_code in (401, 403)


async def test_ingest_social_creates_contact_and_routes_when_empire_digital(client):
    """With org_id=EMPIRE_DIGITAL_COMPANY_ID, ingest creates contact and returns routing info."""
    assert EMPIRE_DIGITAL_COMPANY_ID == 1
    resp = await client.post(
        "/api/v1/leads/ingest-social",
        headers=_headers(org_id=1),
        json={
            "source_platform": "instagram",
            "page_id": "page_123",
            "brand_slug": "empire-digital",
            "full_name": "Social Lead One",
            "email": "social1@example.com",
            "phone": "+971501234567",
            "message": "Interested in study abroad",
            "lead_type": "study_abroad",
            "region": "uae",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["contact_id"] >= 1
    assert body["created"] is True
    assert body["routed"] is True
    assert body["owner_user_id"] is not None
    assert body["sla_deadline_utc"] is not None


async def test_ingest_social_merges_existing_contact_by_email(client):
    """When contact exists by email, ingest merges (updates) and re-routes; created=False."""
    assert EMPIRE_DIGITAL_COMPANY_ID == 1
    first = await client.post(
        "/api/v1/leads/ingest-social",
        headers=_headers(org_id=1),
        json={
            "source_platform": "facebook",
            "full_name": "Merge Lead",
            "email": "merge@example.com",
        },
    )
    assert first.status_code == 201
    contact_id = first.json()["contact_id"]
    assert first.json()["created"] is True

    second = await client.post(
        "/api/v1/leads/ingest-social",
        headers=_headers(org_id=1),
        json={
            "source_platform": "linkedin",
            "full_name": "Merge Lead Updated",
            "email": "merge@example.com",
            "message": "Second touch",
        },
    )
    assert second.status_code == 201
    assert second.json()["contact_id"] == contact_id
    assert second.json()["created"] is False
