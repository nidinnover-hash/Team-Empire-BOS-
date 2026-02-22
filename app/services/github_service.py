"""
GitHub Sync Service — fetch open PRs and issues and upsert into the local Task table.

Stores the Personal Access Token in Integration.config_json["access_token"] so it is
automatically encrypted/decrypted by token_crypto.encrypt_config / decrypt_config.

Syncs:
  • Open pull requests  → Task(external_source="github_pr")
  • Open bug issues     → Task(external_source="github_issue")

Only repos pushed within the last MAX_REPO_AGE_DAYS days are included to avoid
iterating stale/archived repos.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.services import integration as integration_service
from app.tools.github import (
    get_authenticated_user,
    get_issues,
    get_pull_requests,
    list_repos,
)

logger = logging.getLogger(__name__)

_GITHUB_TYPE = "github"
_MAX_REPO_AGE_DAYS = 90   # ignore repos not pushed in the last 90 days
_MAX_REPOS = 30            # hard cap to avoid excessive API calls


async def get_github_status(db: AsyncSession, org_id: int) -> dict[str, Any]:
    """Return connection status for the GitHub integration."""
    item = await integration_service.get_integration_by_type(db, org_id, _GITHUB_TYPE)
    if item is None:
        return {"connected": False, "last_sync_at": None, "login": None, "repos_tracked": None}
    cfg = item.config_json or {}
    return {
        "connected": item.status == "connected",
        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        "login": cfg.get("login"),
        "repos_tracked": cfg.get("repos_tracked"),
    }


async def connect_github(
    db: AsyncSession, org_id: int, api_token: str
) -> dict[str, Any]:
    """
    Verify the GitHub PAT, then store it encrypted in the Integration table.
    Returns the integration info dict on success; raises on auth failure.
    """
    user_info = await get_authenticated_user(api_token)

    config_json = {
        "access_token": api_token,   # encrypt_config() auto-encrypts this field
        "login": user_info.get("login", ""),
        "user_id": user_info.get("id"),
        "name": user_info.get("name", ""),
        "repos_tracked": 0,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }

    item = await integration_service.connect_integration(
        db,
        organization_id=org_id,
        integration_type=_GITHUB_TYPE,
        config_json=config_json,
    )
    return {
        "id": item.id,
        "status": item.status,
        "login": config_json["login"],
    }


async def sync_github(db: AsyncSession, org_id: int) -> dict[str, Any]:
    """
    Fetch open PRs and bug issues from GitHub and upsert into the local Task table.

    Returns {"prs_synced": N, "issues_synced": M, "error": None} on success.
    """
    item = await integration_service.get_integration_by_type(db, org_id, _GITHUB_TYPE)
    if item is None or item.status != "connected":
        return {"prs_synced": 0, "issues_synced": 0, "error": "GitHub integration is not connected"}

    cfg = item.config_json or {}
    token = cfg.get("access_token")

    if not token:
        return {"prs_synced": 0, "issues_synced": 0, "error": "Missing access_token in GitHub config"}

    prs_synced = 0
    issues_synced = 0
    repos_tracked = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=_MAX_REPO_AGE_DAYS)

    try:
        repos = await list_repos(token, per_page=_MAX_REPOS)
        active_repos = []
        for repo in repos:
            pushed_at_str = repo.get("pushed_at")
            if pushed_at_str:
                try:
                    pushed_at = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
                    if pushed_at < cutoff:
                        continue
                except Exception:
                    pass
            if not repo.get("archived") and not repo.get("disabled"):
                active_repos.append(repo)

        repos_tracked = len(active_repos)

        for repo in active_repos:
            owner = repo.get("owner", {}).get("login", "")
            name = repo.get("name", "")
            if not owner or not name:
                continue

            # Sync open PRs
            prs = await get_pull_requests(token, owner, name)
            for pr in prs:
                await _upsert_pr(db, org_id, owner, name, pr)
                prs_synced += 1

            # Sync open bug/critical issues
            issues = await get_issues(token, owner, name, labels="bug")
            for issue in issues:
                await _upsert_issue(db, org_id, owner, name, issue)
                issues_synced += 1

    except Exception as exc:
        logger.warning("GitHub sync failed: %s", type(exc).__name__)
        return {"prs_synced": prs_synced, "issues_synced": issues_synced, "error": type(exc).__name__}

    # Update config with repos_tracked count + mark sync time
    cfg["repos_tracked"] = repos_tracked
    item.config_json = cfg
    await integration_service.mark_sync_time(db, item)
    return {"prs_synced": prs_synced, "issues_synced": issues_synced, "error": None}


async def _upsert_pr(
    db: AsyncSession, org_id: int, owner: str, repo_name: str, pr: dict[str, Any]
) -> None:
    """Insert or update a GitHub PR as a local Task."""
    pr_id = pr.get("number")
    if not pr_id:
        return

    external_id = f"{owner}/{repo_name}#{pr_id}"
    title = f"[PR] {repo_name}: {(pr.get('title') or 'Untitled')}"[:500]
    author = pr.get("user", {}).get("login", "unknown")
    url = pr.get("html_url", "")
    description = f"Author: @{author}\n{url}"
    is_draft = pr.get("draft", False)
    priority = 2 if is_draft else 3   # high for active PRs, medium for drafts

    await _upsert_task(db, org_id, external_id, "github_pr", title, description, priority)


async def _upsert_issue(
    db: AsyncSession, org_id: int, owner: str, repo_name: str, issue: dict[str, Any]
) -> None:
    """Insert or update a GitHub issue as a local Task."""
    issue_id = issue.get("number")
    if not issue_id:
        return

    external_id = f"{owner}/{repo_name}#{issue_id}"
    title = f"[BUG] {repo_name}: {(issue.get('title') or 'Untitled')}"[:500]
    labels = [lb.get("name", "") for lb in (issue.get("labels") or []) if isinstance(lb, dict)]
    url = issue.get("html_url", "")
    description = f"Labels: {', '.join(labels)}\n{url}"
    priority = 4 if "critical" in labels or "urgent" in labels else 3

    await _upsert_task(db, org_id, external_id, "github_issue", title, description, priority)


async def _upsert_task(
    db: AsyncSession,
    org_id: int,
    external_id: str,
    external_source: str,
    title: str,
    description: str | None,
    priority: int,
) -> None:
    result = await db.execute(
        select(Task).where(
            Task.organization_id == org_id,
            Task.external_source == external_source,
            Task.external_id == external_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.title = title
        existing.description = description
        existing.priority = priority
        existing.is_done = False  # re-opened if it was closed
    else:
        task = Task(
            organization_id=org_id,
            title=title,
            description=description,
            priority=priority,
            category="business",
            is_done=False,
            external_id=external_id,
            external_source=external_source,
        )
        db.add(task)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
