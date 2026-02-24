"""
Dedicated GitHub endpoints for governance + CEO monitoring.

All endpoints require CEO or ADMIN role.
Mounted at /api/v1/github/ (separate from /api/v1/integrations/github/).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.github import (
    GitHubCEOSummary,
    GitHubCEOSyncResult,
    GitHubRiskReport,
    GovernanceApplyResponse,
)
from app.services import github_ceo_sync, github_governance

router = APIRouter(prefix="/github", tags=["github-governance"])


@router.post("/apply-governance", response_model=GovernanceApplyResponse)
async def apply_governance(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GovernanceApplyResponse:
    """
    Apply GitHub organization governance: teams, permissions, branch protection,
    CODEOWNERS, PR/issue templates. Idempotent — safe to run repeatedly.
    Requires a connected GitHub PAT with admin:org + repo scopes.
    """
    org_id = int(actor["org_id"])
    policy = github_governance.build_empireoe_policy()
    report = await github_governance.apply_governance(db, org_id, policy)

    await record_action(
        db,
        event_type="github_governance_applied",
        actor_user_id=actor["id"],
        organization_id=org_id,
        entity_type="integration",
        entity_id=None,
        payload_json={
            "org": policy.org,
            "teams": len(report.teams),
            "repos_protected": len(report.branch_protections),
            "errors": len(report.errors),
        },
    )

    return GovernanceApplyResponse(
        teams=report.teams,
        permissions=report.permissions,
        branch_protections=report.branch_protections,
        codeowners=report.codeowners,
        templates=report.templates,
        errors=report.errors,
    )


@router.post("/ceo-sync", response_model=GitHubCEOSyncResult)
async def ceo_sync(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubCEOSyncResult:
    """
    Deep GitHub sync for CEO monitoring: repos, PRs, reviews, commits, workflows.
    Takes longer than regular sync (1-2 min depending on org size).
    """
    org_id = int(actor["org_id"])
    result = await github_ceo_sync.run_ceo_sync(db, org_id)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    await record_action(
        db,
        event_type="github_ceo_sync",
        actor_user_id=actor["id"],
        organization_id=org_id,
        entity_type="integration",
        entity_id=None,
        payload_json={
            "repos": result["repos_synced"],
            "prs": result["prs_synced"],
            "reviews": result["reviews_synced"],
        },
    )

    return GitHubCEOSyncResult(**result)


@router.get("/summary", response_model=GitHubCEOSummary)
async def github_summary(
    range: str = Query("7d", pattern=r"^\d+d$", max_length=5),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubCEOSummary:
    """
    CEO weekly summary: PR throughput per dev, avg review time, CI failure rate,
    blocked repos, inactive dev alerts, commit leaderboard.
    """
    days = int(range.rstrip("d"))
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="Range must be between 1d and 90d")

    org_id = int(actor["org_id"])
    summary = await github_ceo_sync.get_ceo_summary(db, org_id, days=days)
    return GitHubCEOSummary(**summary)


@router.get("/risks", response_model=GitHubRiskReport)
async def github_risks(
    range: str = Query("7d", pattern=r"^\d+d$", max_length=5),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubRiskReport:
    """
    Risk detection: PRs without reviews, failing CI, bus factor repos,
    inactive devs.
    """
    days = int(range.rstrip("d"))
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="Range must be between 1d and 90d")

    org_id = int(actor["org_id"])
    risks = await github_ceo_sync.get_risks(db, org_id, days=days)
    return GitHubRiskReport(**risks)
