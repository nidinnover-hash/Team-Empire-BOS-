"""Tests for GitHub governance + CEO monitoring endpoints."""
from unittest.mock import AsyncMock, patch

from app.core.security import create_access_token
from app.services import github_service


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 1, "email": "ceo@org.com", "role": "CEO", "org_id": org_id})
    return {"Authorization": f"Bearer {token}"}


# ── Helper: connect GitHub in test DB ────────────────────────────────────────

async def _connect_github(client):
    with (
        patch.object(github_service, "get_authenticated_user", new_callable=AsyncMock, return_value={"login": "nidin-cyber", "id": 1, "name": "Nidin"}),
        patch.object(github_service, "list_repos", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.post(
            "/api/v1/integrations/github/connect",
            json={"api_token": "ghp_test_token_12345"},
            headers=_ceo_headers(),
        )
        assert resp.status_code == 201


# ── Governance Apply ─────────────────────────────────────────────────────────

async def test_apply_governance_rejects_staff_role(client):
    """STAFF users cannot apply governance."""
    staff_token = create_access_token({"id": 2, "email": "staff@org.com", "role": "STAFF", "org_id": 1})
    resp = await client.post(
        "/api/v1/github/apply-governance",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert resp.status_code == 403


async def test_apply_governance_no_github_connected(client):
    """When GitHub is not connected, returns error in report."""
    resp = await client.post("/api/v1/github/apply-governance", headers=_ceo_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["errors"]) > 0
    assert data["errors"][0]["step"] == "auth"


async def test_apply_governance_success(client):
    """Mock all GitHub API calls and verify structured report."""
    await _connect_github(client)

    fake_team = {"id": 1, "slug": "tech-leads", "name": "tech-leads"}
    fake_repos = [
        {"full_name": "empireoe-ai/webapp", "name": "webapp", "archived": False, "disabled": False, "default_branch": "main"},
    ]

    with (
        patch("app.tools.github_admin.ensure_team", new_callable=AsyncMock, return_value={"action": "created", "team": fake_team}),
        patch("app.tools.github_admin.ensure_team_member", new_callable=AsyncMock, return_value={"username": "sharonempire", "state": "active", "role": "member"}),
        patch("app.tools.github_admin.list_org_repos", new_callable=AsyncMock, return_value=fake_repos),
        patch("app.tools.github_admin.ensure_team_repo_permission", new_callable=AsyncMock, return_value={"repo": "empireoe-ai/webapp", "team": "tech-leads", "permission": "admin"}),
        patch("app.tools.github_admin.ensure_branch_protection", new_callable=AsyncMock, return_value={"repo": "empireoe-ai/webapp", "branch": "main", "status": "protected"}),
        patch("app.tools.github_admin.ensure_codeowners", new_callable=AsyncMock, return_value={"repo": "empireoe-ai/webapp", "file": ".github/CODEOWNERS", "action": "created"}),
        patch("app.tools.github_admin.ensure_repo_file", new_callable=AsyncMock, return_value={"repo": "empireoe-ai/webapp", "file": ".github/pull_request_template.md", "action": "created"}),
    ):
        resp = await client.post("/api/v1/github/apply-governance", headers=_ceo_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["teams"]) >= 1
    assert len(data["branch_protections"]) >= 1
    assert len(data["codeowners"]) >= 1
    assert isinstance(data["errors"], list)


# ── CEO Sync ─────────────────────────────────────────────────────────────────

async def test_ceo_sync_not_connected(client):
    resp = await client.post("/api/v1/github/ceo-sync", headers=_ceo_headers())
    assert resp.status_code == 400
    assert "not connected" in resp.json()["detail"].lower()


async def test_ceo_sync_success(client):
    """Mock GitHub API and run CEO sync."""
    await _connect_github(client)

    fake_repos = [
        {
            "full_name": "empireoe-ai/webapp",
            "name": "webapp",
            "owner": {"login": "empireoe-ai"},
            "default_branch": "main",
            "private": False,
            "archived": False,
            "disabled": False,
            "language": "Python",
            "open_issues_count": 3,
            "stargazers_count": 0,
            "pushed_at": "2026-02-20T10:00:00Z",
        },
    ]
    fake_prs = [
        {
            "number": 42,
            "title": "Add user auth",
            "user": {"login": "akshayempireoe"},
            "state": "open",
            "draft": False,
            "additions": 100,
            "deletions": 20,
            "changed_files": 5,
            "review_comments": 2,
            "html_url": "https://github.com/empireoe-ai/webapp/pull/42",
            "created_at": "2026-02-18T10:00:00Z",
            "updated_at": "2026-02-20T10:00:00Z",
            "merged_at": None,
            "closed_at": None,
        },
    ]

    with (
        patch("app.services.github_ceo_sync.list_repos", new_callable=AsyncMock, return_value=fake_repos),
        patch("app.tools.github_admin.list_org_repos", new_callable=AsyncMock, return_value=fake_repos),
        patch("app.tools.github_admin.list_org_members", new_callable=AsyncMock, return_value=[{"login": "akshayempireoe", "id": 2}]),
        patch("app.services.github_ceo_sync.get_pull_requests", new_callable=AsyncMock, return_value=fake_prs),
        patch("app.tools.github_admin.get_pr_reviews", new_callable=AsyncMock, return_value=[]),
        patch("app.tools.github_admin.get_repo_commits", new_callable=AsyncMock, return_value=[]),
        patch("app.services.github_ceo_sync.get_workflow_runs", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.post("/api/v1/github/ceo-sync", headers=_ceo_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["repos_synced"] >= 1
    assert data["prs_synced"] >= 1
    assert data["error"] is None


# ── Summary + Risks ──────────────────────────────────────────────────────────

async def test_summary_empty_db(client):
    """Summary on empty DB returns zeros gracefully."""
    resp = await client.get("/api/v1/github/summary?range=7d", headers=_ceo_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["range_days"] == 7
    assert data["pr_throughput"] == []
    assert data["ci_failure_rate_pct"] == 0
    assert data["inactive_devs"] == []


async def test_risks_empty_db(client):
    resp = await client.get("/api/v1/github/risks?range=7d", headers=_ceo_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_risks"] == 0
    assert data["risks"] == []


async def test_summary_invalid_range(client):
    resp = await client.get("/api/v1/github/summary?range=200d", headers=_ceo_headers())
    assert resp.status_code == 400


async def test_risks_invalid_range(client):
    resp = await client.get("/api/v1/github/risks?range=0d", headers=_ceo_headers())
    assert resp.status_code == 400


# ── Governance Unit Tests ────────────────────────────────────────────────────

async def test_governance_policy_has_correct_teams():
    from app.services.github_governance import build_empireoe_policy
    policy = build_empireoe_policy()
    team_names = {t.name for t in policy.teams}
    assert "tech-leads" in team_names
    assert "developers" in team_names
    tech_leads = next(t for t in policy.teams if t.name == "tech-leads")
    assert "sharonempire" in tech_leads.members
    developers = next(t for t in policy.teams if t.name == "developers")
    assert "akshayempireoe" in developers.members
    assert "sanjayempire" in developers.members


async def test_governance_policy_branch_protection():
    from app.services.github_governance import build_empireoe_policy
    policy = build_empireoe_policy()
    bp = policy.branch_protection
    assert bp.required_approvals >= 1
    assert bp.block_force_pushes is True
    assert bp.require_code_owner_reviews is True
    assert "tech-leads" in bp.restrict_push_teams


async def test_governance_codeowners_content():
    from app.services.github_governance import build_empireoe_policy
    policy = build_empireoe_policy()
    assert "@sharonempire" in policy.codeowners_content
    assert "@nidin-cyber" in policy.codeowners_content
