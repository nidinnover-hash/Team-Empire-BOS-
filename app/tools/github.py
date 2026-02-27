"""
GitHub REST API v3 client — async httpx, no DB or settings dependencies.

Authenticates with a Personal Access Token (classic ghp_ or fine-grained github_pat_).
Classic PAT scopes needed: repo, read:user
Fine-grained PAT permissions needed: Contents (read), Issues (read), Pull requests (read)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.github.com"
_TIMEOUT = 20.0
_ACCEPT = "application/vnd.github+json"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": _ACCEPT,
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_authenticated_user(token: str) -> dict[str, Any]:
    """
    Verify the PAT and return the authenticated user's profile.

    Tries GET /user first (works for classic PATs and fine-grained PATs with
    Account: Email read permission). If that returns 403/404 (fine-grained PATs
    without Account permission), falls back to GET /user/repos to confirm the
    token is valid and extracts the owner login from the first repo.

    Raises ValueError on a hard 401 (bad/expired token).
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/user", headers=_headers(token))

        # Hard auth failure — token is invalid
        if resp.status_code == 401:
            resp.raise_for_status()

        # Fine-grained PATs without Account permissions return 403 on /user
        if resp.status_code in (403, 404):
            logger.debug("GET /user returned %d — trying /user/repos fallback", resp.status_code)
            repos_resp = await client.get(
                f"{_BASE}/user/repos",
                headers=_headers(token),
                params={"per_page": 1, "sort": "pushed"},
            )
            repos_resp.raise_for_status()
            repos = repos_resp.json()
            if repos and isinstance(repos, list) and repos[0].get("owner"):
                owner = repos[0]["owner"]
                return {
                    "login": owner.get("login", ""),
                    "id": owner.get("id"),
                    "name": owner.get("login", ""),
                }
            # Token is valid but no repos — still accept it
            return {"login": "unknown", "id": None, "name": ""}

        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, dict) else {}


async def list_repos(
    token: str,
    per_page: int = 50,
) -> list[dict[str, Any]]:
    """
    List the authenticated user's repos (owner + member), sorted by last push.
    Capped at per_page (max 100).
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/user/repos",
            headers=_headers(token),
            params={"type": "all", "sort": "pushed", "per_page": per_page},
        )
        resp.raise_for_status()
        data = resp.json()
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


async def get_pull_requests(
    token: str,
    owner: str,
    repo: str,
    state: str = "open",
    per_page: int = 30,
) -> list[dict[str, Any]]:
    """Return open pull requests for a repository."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/repos/{owner}/{repo}/pulls",
            headers=_headers(token),
            params={"state": state, "per_page": per_page, "sort": "updated"},
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return [pr for pr in data if isinstance(pr, dict)] if isinstance(data, list) else []


async def get_workflow_runs(
    token: str,
    owner: str,
    repo: str,
    per_page: int = 20,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """
    List recent GitHub Actions workflow runs for a repository.
    Returns run id, name, status, conclusion, head_branch, created_at, updated_at, etc.
    """
    params: dict[str, Any] = {"per_page": per_page}
    if status:
        params["status"] = status
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/repos/{owner}/{repo}/actions/runs",
            headers=_headers(token),
            params=params,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        runs = data.get("workflow_runs", [])
        return [r for r in runs if isinstance(r, dict)]


async def get_deployments(
    token: str,
    owner: str,
    repo: str,
    per_page: int = 15,
) -> list[dict[str, Any]]:
    """List recent deployments for a repository."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/repos/{owner}/{repo}/deployments",
            headers=_headers(token),
            params={"per_page": per_page},
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


async def get_issues(
    token: str,
    owner: str,
    repo: str,
    state: str = "open",
    labels: str = "",
    per_page: int = 30,
) -> list[dict[str, Any]]:
    """
    Return open issues for a repository.
    Pass labels="bug" to filter by label.
    GitHub issues API also returns PRs — filter them out with pull_request key check.
    """
    params: dict[str, Any] = {"state": state, "per_page": per_page, "sort": "updated"}
    if labels:
        params["labels"] = labels

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/repos/{owner}/{repo}/issues",
            headers=_headers(token),
            params=params,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        # Exclude pull requests (GitHub returns them in /issues too)
        return [i for i in data if isinstance(i, dict) and "pull_request" not in i]
