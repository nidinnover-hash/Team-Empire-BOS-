from datetime import datetime, timezone

from app.db.base import Base
from app.db.session import engine
from app.db.session import AsyncSessionLocal
from app.models.ceo_control import GitHubRepoSnapshot, GitHubRoleSnapshot
from app.services import compliance_engine


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
