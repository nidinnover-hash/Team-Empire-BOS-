"""
GitHub REST API client for organization governance operations.

All functions are idempotent — safe to call repeatedly.
Authenticates with a PAT that has admin:org, repo, admin:org_hook scopes.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.github.com"
_TIMEOUT = 25.0
_ACCEPT = "application/vnd.github+json"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": _ACCEPT,
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ── Teams ────────────────────────────────────────────────────────────────────

async def ensure_team(
    token: str,
    org: str,
    team_name: str,
    description: str = "",
    privacy: str = "closed",
) -> dict[str, Any]:
    """Create a team if it doesn't exist, or return the existing one."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        slug = team_name.lower().replace(" ", "-")
        # Try to get existing team
        resp = await client.get(
            f"{_BASE}/orgs/{org}/teams/{slug}",
            headers=_headers(token),
        )
        if resp.status_code == 200:
            return {"action": "exists", "team": resp.json()}

        # Create team
        resp = await client.post(
            f"{_BASE}/orgs/{org}/teams",
            headers=_headers(token),
            json={
                "name": team_name,
                "description": description,
                "privacy": privacy,
            },
        )
        resp.raise_for_status()
        return {"action": "created", "team": resp.json()}


async def ensure_team_member(
    token: str,
    org: str,
    team_slug: str,
    username: str,
    role: str = "member",
) -> dict[str, Any]:
    """Add a user to a team (idempotent). role: member or maintainer."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.put(
            f"{_BASE}/orgs/{org}/teams/{team_slug}/memberships/{username}",
            headers=_headers(token),
            json={"role": role},
        )
        resp.raise_for_status()
        data = resp.json()
        return {"username": username, "state": data.get("state"), "role": data.get("role")}


# ── Repo Permissions ─────────────────────────────────────────────────────────

async def ensure_team_repo_permission(
    token: str,
    org: str,
    team_slug: str,
    repo_full_name: str,
    permission: str = "push",
) -> dict[str, Any]:
    """
    Grant a team access to a repo. permission: pull, push, admin, maintain, triage.
    """
    owner, repo = repo_full_name.split("/", 1)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.put(
            f"{_BASE}/orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}",
            headers=_headers(token),
            json={"permission": permission},
        )
        resp.raise_for_status()
        return {"repo": repo_full_name, "team": team_slug, "permission": permission}


# ── Branch Protection ────────────────────────────────────────────────────────

async def ensure_branch_protection(
    token: str,
    repo_full_name: str,
    branch: str = "main",
    required_approvals: int = 1,
    require_code_owner_reviews: bool = True,
    dismiss_stale_reviews: bool = True,
    require_status_checks: bool = True,
    required_status_contexts: list[str] | None = None,
    enforce_admins: bool = False,
    block_force_pushes: bool = True,
    restrict_push_teams: list[str] | None = None,
    restrict_push_users: list[str] | None = None,
) -> dict[str, Any]:
    """
    Set branch protection rules (idempotent — overwrites current rules).
    """
    owner, repo = repo_full_name.split("/", 1)

    body: dict[str, Any] = {
        "required_pull_request_reviews": {
            "required_approving_review_count": required_approvals,
            "dismiss_stale_reviews": dismiss_stale_reviews,
            "require_code_owner_reviews": require_code_owner_reviews,
        },
        "enforce_admins": enforce_admins,
        "allow_force_pushes": not block_force_pushes,
        "allow_deletions": False,
        "required_linear_history": False,
    }

    if require_status_checks:
        body["required_status_checks"] = {
            "strict": True,
            "contexts": required_status_contexts or [],
        }
    else:
        body["required_status_checks"] = None

    # Restrict who can push to this branch
    if restrict_push_teams or restrict_push_users:
        body["restrictions"] = {
            "users": restrict_push_users or [],
            "teams": restrict_push_teams or [],
            "apps": [],
        }
    else:
        body["restrictions"] = None

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.put(
            f"{_BASE}/repos/{owner}/{repo}/branches/{branch}/protection",
            headers=_headers(token),
            json=body,
        )
        resp.raise_for_status()
        return {"repo": repo_full_name, "branch": branch, "status": "protected"}


# ── CODEOWNERS ───────────────────────────────────────────────────────────────

async def ensure_codeowners(
    token: str,
    repo_full_name: str,
    content: str,
    branch: str = "main",
) -> dict[str, Any]:
    """
    Create or update .github/CODEOWNERS file in the repo.
    """
    owner, repo = repo_full_name.split("/", 1)
    path = ".github/CODEOWNERS"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # Check if file exists to get its SHA (needed for update)
        get_resp = await client.get(
            f"{_BASE}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(token),
            params={"ref": branch},
        )
        sha = None
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")

        body: dict[str, Any] = {
            "message": "chore: update CODEOWNERS via governance automation",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        resp = await client.put(
            f"{_BASE}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(token),
            json=body,
        )
        resp.raise_for_status()
        action = "updated" if sha else "created"
        return {"repo": repo_full_name, "file": path, "action": action}


# ── File Templates ───────────────────────────────────────────────────────────

async def ensure_repo_file(
    token: str,
    repo_full_name: str,
    file_path: str,
    content: str,
    commit_message: str,
    branch: str = "main",
) -> dict[str, Any]:
    """Create or update any file in the repo (used for PR/issue templates)."""
    owner, repo = repo_full_name.split("/", 1)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        get_resp = await client.get(
            f"{_BASE}/repos/{owner}/{repo}/contents/{file_path}",
            headers=_headers(token),
            params={"ref": branch},
        )
        sha = None
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")

        body: dict[str, Any] = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        resp = await client.put(
            f"{_BASE}/repos/{owner}/{repo}/contents/{file_path}",
            headers=_headers(token),
            json=body,
        )
        resp.raise_for_status()
        action = "updated" if sha else "created"
        return {"repo": repo_full_name, "file": file_path, "action": action}


# ── Org Helpers ──────────────────────────────────────────────────────────────

async def list_org_repos(
    token: str,
    org: str,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """List all repos in an organization."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/orgs/{org}/repos",
            headers=_headers(token),
            params={"type": "all", "per_page": per_page, "sort": "pushed"},
        )
        resp.raise_for_status()
        data = resp.json()
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


async def list_org_members(
    token: str,
    org: str,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """List all members of an organization."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/orgs/{org}/members",
            headers=_headers(token),
            params={"per_page": per_page},
        )
        resp.raise_for_status()
        data = resp.json()
        return [m for m in data if isinstance(m, dict)] if isinstance(data, list) else []


async def get_pr_reviews(
    token: str,
    repo_full_name: str,
    pr_number: int,
    per_page: int = 30,
) -> list[dict[str, Any]]:
    """List reviews for a pull request."""
    owner, repo = repo_full_name.split("/", 1)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=_headers(token),
            params={"per_page": per_page},
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


async def get_repo_commits(
    token: str,
    repo_full_name: str,
    since: str | None = None,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """List recent commits for a repo. since: ISO8601 datetime string."""
    owner, repo = repo_full_name.split("/", 1)
    params: dict[str, Any] = {"per_page": per_page}
    if since:
        params["since"] = since

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/repos/{owner}/{repo}/commits",
            headers=_headers(token),
            params=params,
        )
        if resp.status_code in (404, 409):  # 409 = empty repo
            return []
        resp.raise_for_status()
        data = resp.json()
        return [c for c in data if isinstance(c, dict)] if isinstance(data, list) else []
