"""Tests for Command Center config, industry panels, and role-based views."""

from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app as fastapi_app
from app.models.organization import Organization
from app.models.user import User


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


def _super_admin_headers():
    token = create_access_token({
        "id": 1, "email": "ceo@org1.com", "role": "CEO",
        "org_id": 1, "token_version": 1, "is_super_admin": True,
    })
    return {"Authorization": f"Bearer {token}"}


async def _create_user_with_role(role: str, user_id: int, email: str) -> dict:
    """Create a DB user with the given role and return auth headers."""
    from sqlalchemy import select as _sel

    session, agen = await _get_session()
    try:
        existing = await session.get(User, user_id)
        if existing is not None:
            existing.role = role
        else:
            # Check email uniqueness
            by_email = (await session.execute(
                _sel(User).where(User.email == email)
            )).scalar_one_or_none()
            if by_email is not None:
                by_email.role = role
                user_id = by_email.id
            else:
                session.add(User(
                    id=user_id,
                    organization_id=1,
                    name=f"{role} User",
                    email=email,
                    password_hash=hash_password("TestPassword2026!"),
                    role=role,
                    is_active=True,
                ))
        await session.commit()
    finally:
        await agen.aclose()
    token = create_access_token({
        "id": user_id, "email": email, "role": role,
        "org_id": 1, "token_version": 1,
    })
    return {"Authorization": f"Bearer {token}"}


# ── GET config ───────────────────────────────────────────────────────────────

async def test_get_command_center_config_defaults(client):
    resp = await client.get(
        "/api/v1/admin/orgs/1/command-center-config",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "weights" in body
    assert "thresholds" in body
    assert "levels" in body
    assert body["weights"]["critical_tokens"] == 3
    assert body["levels"]["amber"] == 2
    assert body["levels"]["red"] == 4


# ── PATCH config ─────────────────────────────────────────────────────────────

async def test_patch_command_center_config_updates_weights(client):
    resp = await client.patch(
        "/api/v1/admin/orgs/1/command-center-config",
        json={"weights": {"critical_tokens": 5}},
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["weights"]["critical_tokens"] == 5
    # Other weights preserved
    assert resp.json()["weights"]["warning_tokens"] == 1


async def test_patch_command_center_config_updates_thresholds(client):
    resp = await client.patch(
        "/api/v1/admin/orgs/1/command-center-config",
        json={"thresholds": {"unread_emails_min": 100}},
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["thresholds"]["unread_emails_min"] == 100


async def test_patch_command_center_config_updates_levels(client):
    resp = await client.patch(
        "/api/v1/admin/orgs/1/command-center-config",
        json={"levels": {"amber": 3, "red": 6}},
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["levels"]["amber"] == 3
    assert resp.json()["levels"]["red"] == 6


# ── POST reset ───────────────────────────────────────────────────────────────

async def test_reset_command_center_config(client):
    # First modify
    await client.patch(
        "/api/v1/admin/orgs/1/command-center-config",
        json={"weights": {"critical_tokens": 99}},
        headers=_super_admin_headers(),
    )
    # Then reset
    resp = await client.post(
        "/api/v1/admin/orgs/1/command-center-config/reset",
        headers=_super_admin_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["weights"]["critical_tokens"] == 3  # back to default


# ── Incident endpoint new fields ─────────────────────────────────────────────

async def test_incident_command_mode_returns_view_type(client):
    resp = await client.get("/api/v1/ops/incident/command-mode")
    assert resp.status_code == 200
    body = resp.json()
    assert "view_type" in body
    assert body["view_type"] in ("strategic", "operational", "team", "technical")


async def test_incident_command_mode_returns_industry_panels(client):
    resp = await client.get("/api/v1/ops/incident/command-mode")
    assert resp.status_code == 200
    body = resp.json()
    assert "industry_panels" in body
    assert isinstance(body["industry_panels"], list)


# ── Industry panels based on org type ────────────────────────────────────────

async def test_incident_panels_for_education_org(client):
    session, agen = await _get_session()
    try:
        org = await session.get(Organization, 1)
        org.industry_type = "education"
        await session.commit()
    finally:
        await agen.aclose()

    resp = await client.get("/api/v1/ops/incident/command-mode")
    assert resp.status_code == 200
    panels = resp.json()["industry_panels"]
    assert len(panels) >= 1
    keys = [p["key"] for p in panels]
    assert "active_enrollments" in keys


async def test_incident_panels_for_saas_org(client):
    session, agen = await _get_session()
    try:
        org = await session.get(Organization, 1)
        org.industry_type = "saas"
        await session.commit()
    finally:
        await agen.aclose()

    resp = await client.get("/api/v1/ops/incident/command-mode")
    assert resp.status_code == 200
    panels = resp.json()["industry_panels"]
    keys = [p["key"] for p in panels]
    assert "mrr" in keys


# ── Role-based view filtering ────────────────────────────────────────────────

async def test_ceo_gets_strategic_view(client):
    resp = await client.get("/api/v1/ops/incident/command-mode")
    assert resp.status_code == 200
    assert resp.json()["view_type"] == "strategic"


async def test_manager_gets_team_view(client):
    headers = await _create_user_with_role("MANAGER", 100, "manager@org1.com")
    resp = await client.get("/api/v1/ops/incident/command-mode", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["view_type"] == "team"
    assert "sync_error_integrations" not in body["triggers"]
    assert "webhook_failures_24h" not in body["triggers"]


async def test_developer_gets_technical_view(client):
    headers = await _create_user_with_role("DEVELOPER", 101, "dev@org1.com")
    resp = await client.get("/api/v1/ops/incident/command-mode", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["view_type"] == "technical"
    assert "pending_approvals" not in body["triggers"]
    assert "unread_emails" not in body["triggers"]
    assert body["industry_panels"] == []


# ── Custom scoring affects level ─────────────────────────────────────────────

async def test_custom_levels_affect_incident_level(client):
    # Set very high thresholds so score=0 → green
    await client.patch(
        "/api/v1/admin/orgs/1/command-center-config",
        json={"levels": {"amber": 100, "red": 200}},
        headers=_super_admin_headers(),
    )
    resp = await client.get("/api/v1/ops/incident/command-mode")
    assert resp.status_code == 200
    assert resp.json()["incident_level"] == "green"

    # Reset
    await client.post(
        "/api/v1/admin/orgs/1/command-center-config/reset",
        headers=_super_admin_headers(),
    )
