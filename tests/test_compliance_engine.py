"""
Tests for the compliance engine service.

Uses an isolated in-memory SQLite database per test (via the ``db`` fixture)
instead of the application's real engine/session.
"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models.ceo_control import (
    ClickUpTaskSnapshot,
    DigitalOceanTeamSnapshot,
    GitHubIdentityMap,
    GitHubRepoSnapshot,
    GitHubRoleSnapshot,
)
from app.services import compliance_engine


@pytest_asyncio.fixture
async def db():
    """Yield an isolated AsyncSession backed by a fresh in-memory SQLite DB."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_compliance_flags_unauthorized_github_owner(db):
    now = datetime.now(UTC)
    db.add(
        GitHubRoleSnapshot(
            organization_id=1,
            org_login="EmpireO.AI",
            github_login="random-owner",
            org_role="owner",
            repo_name=None,
            repo_permission=None,
            synced_at=now,
        )
    )
    await db.commit()
    result = await compliance_engine.run_compliance(db, 1)
    titles = {v["title"] for v in result["violations"]}
    assert "Unauthorized GitHub org owner" in titles


async def test_compliance_flags_unprotected_branch(db):
    now = datetime.now(UTC)
    db.add(
        GitHubRepoSnapshot(
            organization_id=1,
            repo_name="EmpireO.AI/core",
            default_branch="main",
            is_protected=False,
            requires_reviews=False,
            required_checks_enabled=False,
            synced_at=now,
        )
    )
    await db.commit()
    result = await compliance_engine.run_compliance(db, 1)
    titles = {v["title"] for v in result["violations"]}
    assert "Critical repo branch protection insufficient" in titles


async def test_compliance_skips_company_owner_rule_for_personal_org(db, monkeypatch):
    monkeypatch.setattr(settings, "PERSONAL_ORG_ID", 99)
    now = datetime.now(UTC)
    db.add(
        GitHubRoleSnapshot(
            organization_id=99,
            org_login="PersonalOrg",
            github_login="personal-owner",
            org_role="owner",
            repo_name=None,
            repo_permission=None,
            synced_at=now,
        )
    )
    await db.commit()
    result = await compliance_engine.run_compliance(db, 99)
    titles = {v["title"] for v in result["violations"]}
    assert "Unauthorized GitHub org owner" not in titles


async def test_compliance_flags_personal_email_in_company_do_team(db, monkeypatch):
    monkeypatch.setattr(settings, "PERSONAL_ORG_ID", 99)
    now = datetime.now(UTC)
    db.add(
        DigitalOceanTeamSnapshot(
            organization_id=1,
            email="nidinnover@gmail.com",
            role="member",
            synced_at=now,
        )
    )
    await db.commit()
    result = await compliance_engine.run_compliance(db, 1)
    titles = {v["title"] for v in result["violations"]}
    assert "Personal email present in company infra access" in titles


async def test_compliance_flags_personal_email_mapped_to_company_github_identity(db, monkeypatch):
    monkeypatch.setattr(settings, "PERSONAL_ORG_ID", 99)
    now = datetime.now(UTC)
    db.add(
        GitHubIdentityMap(
            organization_id=1,
            company_email="nidinnover@gmail.com",
            github_login="nidin-personal",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        GitHubRoleSnapshot(
            organization_id=1,
            org_login="EmpireO.AI",
            github_login="nidin-personal",
            org_role="member",
            repo_name="EmpireO.AI/core",
            repo_permission="write",
            synced_at=now,
        )
    )
    await db.commit()
    result = await compliance_engine.run_compliance(db, 1)
    titles = {v["title"] for v in result["violations"]}
    assert "Personal email mapped to company GitHub identity" in titles


async def test_compliance_flags_owner_invite_created_by_non_owner(db, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_ORG", "codnov-ai")
    now = datetime.now(UTC)
    db.add(
        GitHubIdentityMap(
            organization_id=1,
            company_email="sharon@empireoe.com",
            github_login="sharonempire",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        GitHubRoleSnapshot(
            organization_id=1,
            org_login="codnov-ai",
            github_login="sharonempire",
            org_role="member",
            repo_name=None,
            repo_permission=None,
            synced_at=now,
        )
    )
    await db.commit()

    async def fake_get_integration_by_type(*_args, **_kwargs):
        return SimpleNamespace(status="connected", config_json={"access_token": "ghp_test"})

    async def fake_list_org_invitations(*_args, **_kwargs):
        return [
            {
                "email": "admin@empireoe.com",
                "role": "admin",
                "inviter": {"login": "sharonempire"},
            }
        ]

    monkeypatch.setattr(
        compliance_engine.integration_service, "get_integration_by_type", fake_get_integration_by_type
    )
    monkeypatch.setattr(
        compliance_engine.github_admin, "list_org_invitations", fake_list_org_invitations
    )

    result = await compliance_engine.run_compliance(db, 1)
    titles = {v["title"] for v in result["violations"]}
    assert "GitHub owner invitation created by non-owner" in titles


async def test_compliance_allows_configured_personal_owner_exception(db, monkeypatch):
    monkeypatch.setattr(settings, "PERSONAL_ORG_ID", 99)
    monkeypatch.setattr(settings, "COMPLIANCE_ALLOWED_PERSONAL_EMAILS", "nidinnover@gmail.com")
    monkeypatch.setattr(settings, "COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS", True)
    now = datetime.now(UTC)
    db.add(
        DigitalOceanTeamSnapshot(
            organization_id=1,
            email="nidinnover@gmail.com",
            role="owner",
            synced_at=now,
        )
    )
    await db.commit()
    result = await compliance_engine.run_compliance(db, 1)
    titles = {v["title"] for v in result["violations"]}
    assert "Unauthorized DigitalOcean owner" not in titles
    assert "Personal email present in company infra access" not in titles


async def test_compliance_flags_blocked_critical_task_over_3_days(db):
    now = datetime.now(UTC)
    db.add(
        ClickUpTaskSnapshot(
            organization_id=1,
            external_id="CU-1",
            name="Critical API migration",
            status="blocked",
            assignees='["mano@empireoe.com"]',
            due_date=now,
            priority="high",
            tags='["CEO-PRIORITY"]',
            list_id="L1",
            folder_id="F1",
            url="https://clickup/task/1",
            updated_at_remote=now - timedelta(days=4),
            synced_at=now,
        )
    )
    await db.commit()
    result = await compliance_engine.run_compliance(db, 1)
    titles = {v["title"] for v in result["violations"]}
    assert "Blocked critical task > 3 days" in titles


async def test_compliance_flags_unmapped_github_identity(db):
    now = datetime.now(UTC)
    db.add(
        GitHubRoleSnapshot(
            organization_id=1,
            org_login="EmpireO.AI",
            github_login="unknown-login",
            org_role="member",
            repo_name="EmpireO.AI/core",
            repo_permission="write",
            synced_at=now,
        )
    )
    await db.commit()
    result = await compliance_engine.run_compliance(db, 1)
    titles = {v["title"] for v in result["violations"]}
    assert "GitHub identity mapping missing" in titles
