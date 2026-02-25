from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.db.base import Base
from app.db.session import engine
from app.db.session import AsyncSessionLocal
from app.models.ceo_control import (
    DigitalOceanTeamSnapshot,
    GitHubIdentityMap,
    ClickUpTaskSnapshot,
    GitHubRepoSnapshot,
    GitHubRoleSnapshot,
)
from app.services import compliance_engine
from app.core.config import settings


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_compliance_flags_unauthorized_github_owner():
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
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


async def test_compliance_flags_unprotected_branch():
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
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


async def test_compliance_skips_company_owner_rule_for_personal_org():
    await _ensure_tables()
    previous = settings.PERSONAL_ORG_ID
    settings.PERSONAL_ORG_ID = 99
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
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
    finally:
        settings.PERSONAL_ORG_ID = previous


async def test_compliance_flags_personal_email_in_company_do_team():
    await _ensure_tables()
    previous = settings.PERSONAL_ORG_ID
    settings.PERSONAL_ORG_ID = 99
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
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
    finally:
        settings.PERSONAL_ORG_ID = previous


async def test_compliance_flags_personal_email_mapped_to_company_github_identity():
    await _ensure_tables()
    previous = settings.PERSONAL_ORG_ID
    settings.PERSONAL_ORG_ID = 99
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
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
    finally:
        settings.PERSONAL_ORG_ID = previous


async def test_compliance_flags_owner_invite_created_by_non_owner(monkeypatch):
    await _ensure_tables()
    previous_org = settings.GITHUB_ORG
    settings.GITHUB_ORG = "codnov-ai"
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
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

            monkeypatch.setattr(compliance_engine.integration_service, "get_integration_by_type", fake_get_integration_by_type)
            monkeypatch.setattr(compliance_engine.github_admin, "list_org_invitations", fake_list_org_invitations)

            result = await compliance_engine.run_compliance(db, 1)
            titles = {v["title"] for v in result["violations"]}
            assert "GitHub owner invitation created by non-owner" in titles
    finally:
        settings.GITHUB_ORG = previous_org


async def test_compliance_allows_configured_personal_owner_exception():
    await _ensure_tables()
    prev_personal_org = settings.PERSONAL_ORG_ID
    prev_allowed = settings.COMPLIANCE_ALLOWED_PERSONAL_EMAILS
    prev_allow_owner = settings.COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS
    settings.PERSONAL_ORG_ID = 99
    settings.COMPLIANCE_ALLOWED_PERSONAL_EMAILS = "nidinnover@gmail.com"
    settings.COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS = True
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
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
    finally:
        settings.PERSONAL_ORG_ID = prev_personal_org
        settings.COMPLIANCE_ALLOWED_PERSONAL_EMAILS = prev_allowed
        settings.COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS = prev_allow_owner


async def test_compliance_flags_blocked_critical_task_over_3_days():
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
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


async def test_compliance_flags_unmapped_github_identity():
    await _ensure_tables()
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
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
