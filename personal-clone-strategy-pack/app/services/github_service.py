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
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.resilience import run_with_retry
from app.core.tenant import require_org_id
from app.models.ceo_control import GitHubPRSnapshot, GitHubRepoSnapshot, GitHubRoleSnapshot
from app.models.task import Task
from app.services import github_app_auth
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


def _critical_repos() -> set[str]:
    raw = settings.CRITICAL_GITHUB_REPOS or ""
    return {r.strip().lower() for r in raw.split(",") if r.strip()}


def _parse_gh_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


async def _snapshot_from_installation_token(
    db: AsyncSession, org_id: int, org: str, token: str, repos: list[dict[str, Any]]
) -> None:
    now = datetime.now(timezone.utc)
    if not token or not org:
        return

    await db.execute(delete(GitHubRoleSnapshot).where(GitHubRoleSnapshot.organization_id == org_id))
    await db.execute(delete(GitHubRepoSnapshot).where(GitHubRepoSnapshot.organization_id == org_id))
    await db.execute(delete(GitHubPRSnapshot).where(GitHubPRSnapshot.organization_id == org_id))

    members = await github_app_auth.github_get_json(f"/orgs/{org}/members", token, params={"per_page": 200})
    if isinstance(members, list):
        for m in members:
            if not isinstance(m, dict):
                continue
            login = str(m.get("login") or "")
            role_resp = await github_app_auth.github_get_json(f"/orgs/{org}/memberships/{login}", token)
            role = str((role_resp or {}).get("role") or "")
            db.add(
                GitHubRoleSnapshot(
                    organization_id=org_id,
                    org_login=org,
                    github_login=login,
                    org_role=role,
                    repo_name=None,
                    repo_permission=None,
                    synced_at=now,
                )
            )

    critical = _critical_repos()
    for repo in repos:
        owner = repo.get("owner", {}).get("login", "")
        name = repo.get("name", "")
        full = f"{owner}/{name}".lower() if owner and name else ""
        if critical and full not in critical and name.lower() not in critical:
            continue
        branch = str(repo.get("default_branch") or "main")
        branch_info = await github_app_auth.github_get_json(
            f"/repos/{owner}/{name}/branches/{branch}", token
        )
        protected = bool((branch_info or {}).get("protected"))
        protection = {}
        try:
            protection = await github_app_auth.github_get_json(
                f"/repos/{owner}/{name}/branches/{branch}/protection", token
            )
        except Exception:
            protection = {}
        required_reviews = bool((protection or {}).get("required_pull_request_reviews"))
        required_checks = bool((protection or {}).get("required_status_checks"))
        db.add(
            GitHubRepoSnapshot(
                organization_id=org_id,
                repo_name=f"{owner}/{name}",
                default_branch=branch,
                is_protected=protected,
                requires_reviews=required_reviews,
                required_checks_enabled=required_checks,
                synced_at=now,
            )
        )

        collabs = await github_app_auth.github_get_json(
            f"/repos/{owner}/{name}/collaborators", token, params={"per_page": 200}
        )
        if isinstance(collabs, list):
            for c in collabs:
                if not isinstance(c, dict):
                    continue
                login = str(c.get("login") or "")
                perm = ""
                permissions = c.get("permissions")
                if isinstance(permissions, dict):
                    if permissions.get("admin"):
                        perm = "admin"
                    elif permissions.get("maintain"):
                        perm = "maintain"
                    elif permissions.get("push"):
                        perm = "write"
                    elif permissions.get("pull"):
                        perm = "read"
                db.add(
                    GitHubRoleSnapshot(
                        organization_id=org_id,
                        org_login=org,
                        github_login=login,
                        org_role=None,
                        repo_name=f"{owner}/{name}",
                        repo_permission=perm,
                        synced_at=now,
                    )
                )

        prs = await github_app_auth.github_get_json(
            f"/repos/{owner}/{name}/pulls", token, params={"state": "open", "per_page": 50}
        )
        if isinstance(prs, list):
            for pr in prs:
                if not isinstance(pr, dict):
                    continue
                number = int(pr.get("number") or 0)
                if number <= 0:
                    continue
                reviewers = [r.get("login") for r in (pr.get("requested_reviewers") or []) if isinstance(r, dict)]
                checks_state = str((pr.get("head") or {}).get("ref") or "")
                db.add(
                    GitHubPRSnapshot(
                        organization_id=org_id,
                        repo_name=f"{owner}/{name}",
                        pr_number=number,
                        title=str(pr.get("title") or ""),
                        author=str((pr.get("user") or {}).get("login") or ""),
                        requested_reviewers=json.dumps([r for r in reviewers if r]),
                        created_at_remote=_parse_gh_ts(pr.get("created_at")),
                        updated_at_remote=_parse_gh_ts(pr.get("updated_at")),
                        checks_state=checks_state,
                        url=str(pr.get("html_url") or ""),
                        synced_at=now,
                    )
                )


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
    require_org_id(org_id)
    user_info = await run_with_retry(lambda: get_authenticated_user(api_token))

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
        repos = await run_with_retry(lambda: list_repos(token, per_page=_MAX_REPOS))
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

        # Collect all upsert items first, then batch-load existing tasks
        upsert_batch: list[dict[str, Any]] = []

        for repo in active_repos:
            owner = repo.get("owner", {}).get("login", "")
            name = repo.get("name", "")
            if not owner or not name:
                continue

            # Sync open PRs
            try:
                async def _load_prs(o: str = owner, n: str = name) -> list[dict[str, Any]]:
                    return await get_pull_requests(token, o, n)

                prs = await run_with_retry(_load_prs)
            except Exception as exc:
                logger.warning("GitHub PR fetch failed for %s/%s: %s", owner, name, type(exc).__name__)
                continue
            for pr in prs:
                pr_id = pr.get("number")
                if not pr_id:
                    continue
                ext_id = f"{owner}/{name}#{pr_id}"
                title = f"[PR] {name}: {(pr.get('title') or 'Untitled')}"[:500]
                author = pr.get("user", {}).get("login", "unknown")
                url = pr.get("html_url", "")
                desc = f"Author: @{author}\n{url}"
                is_draft = pr.get("draft", False)
                prio = 2 if is_draft else 3
                upsert_batch.append({"external_id": ext_id, "source": "github_pr", "title": title, "description": desc, "priority": prio, "updated_at_raw": pr.get("updated_at")})

            # Sync open bug/critical issues
            try:
                async def _load_issues(o: str = owner, n: str = name) -> list[dict[str, Any]]:
                    return await get_issues(token, o, n, labels="bug")

                issues = await run_with_retry(_load_issues)
            except Exception as exc:
                logger.warning("GitHub issue fetch failed for %s/%s: %s", owner, name, type(exc).__name__)
                continue
            for issue in issues:
                issue_id = issue.get("number")
                if not issue_id:
                    continue
                ext_id = f"{owner}/{name}#{issue_id}"
                title = f"[BUG] {name}: {(issue.get('title') or 'Untitled')}"[:500]
                labels = [lb.get("name", "") for lb in (issue.get("labels") or []) if isinstance(lb, dict)]
                url = issue.get("html_url", "")
                desc = f"Labels: {', '.join(labels)}\n{url}"
                prio = 4 if "critical" in labels or "urgent" in labels else 3
                upsert_batch.append({"external_id": ext_id, "source": "github_issue", "title": title, "description": desc, "priority": prio, "updated_at_raw": issue.get("updated_at")})

        # Batch-load all existing tasks for this org + sources to avoid N+1
        ext_ids = [item["external_id"] for item in upsert_batch]
        existing_map: dict[tuple[str, str], Task] = {}
        if ext_ids:
            result = await db.execute(
                select(Task).where(
                    Task.organization_id == org_id,
                    Task.external_source.in_(["github_pr", "github_issue"]),
                    Task.external_id.in_(ext_ids),
                )
            )
            for task in result.scalars().all():
                existing_map[(task.external_source, task.external_id)] = task

        # Upsert all items with per-item error handling
        for upsert_item in upsert_batch:
            try:
                key = (upsert_item["source"], upsert_item["external_id"])
                existing = existing_map.get(key)
                if existing:
                    # Skip overwrite if local task was edited after remote update
                    raw_ts = upsert_item.get("updated_at_raw")
                    updated_remote = None
                    if raw_ts:
                        try:
                            updated_remote = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                        except Exception as exc:
                            logger.debug(
                                "GitHub updated_at parse failed for %s: %s",
                                upsert_item["external_id"],
                                type(exc).__name__,
                            )
                    if updated_remote and getattr(existing, "updated_at", None) and existing.updated_at > updated_remote:
                        continue
                    existing.title = upsert_item["title"]
                    existing.description = upsert_item["description"]
                    existing.priority = upsert_item["priority"]
                    existing.is_done = False
                else:
                    task = Task(
                        organization_id=org_id,
                        title=upsert_item["title"],
                        description=upsert_item["description"],
                        priority=upsert_item["priority"],
                        category="business",
                        is_done=False,
                        external_id=upsert_item["external_id"],
                        external_source=upsert_item["source"],
                    )
                    db.add(task)
                if upsert_item["source"] == "github_pr":
                    prs_synced += 1
                else:
                    issues_synced += 1
            except Exception as exc:
                logger.warning("GitHub upsert skipped %s: %s", upsert_item["external_id"], exc)
                continue

        await db.commit()

    except Exception as exc:
        logger.warning("GitHub sync failed: %s", type(exc).__name__)
        await db.rollback()
        return {"prs_synced": prs_synced, "issues_synced": issues_synced, "error": type(exc).__name__}

    # Optional CEO-control snapshot via GitHub App installation token
    try:
        if settings.GITHUB_APP_ID and settings.GITHUB_PRIVATE_KEY_PEM and settings.GITHUB_ORG:
            org_login, install_token, install_id = await github_app_auth.get_installation_token_for_org()
            cfg["org_login"] = org_login
            cfg["installation_id"] = install_id
            await _snapshot_from_installation_token(db, org_id, org_login, install_token, repos)
    except Exception as exc:
        logger.warning("GitHub app snapshot skipped: %s", type(exc).__name__)

    # Update config with repos_tracked count + mark sync time
    cfg["repos_tracked"] = repos_tracked
    item.config_json = cfg
    await integration_service.mark_sync_time(db, item)
    return {"prs_synced": prs_synced, "issues_synced": issues_synced, "error": None}
