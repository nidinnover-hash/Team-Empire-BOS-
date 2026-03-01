"""
GitHub REST API v3 client — async httpx, no DB or settings dependencies.

Authenticates with a Personal Access Token (classic ghp_ or fine-grained github_pat_).
Classic PAT scopes needed: repo, read:user
Fine-grained PAT permissions needed: Contents (read), Issues (read), Pull requests (read)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.github.com"
_TIMEOUT = 20.0
_ACCEPT = "application/vnd.github+json"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": _ACCEPT,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _next_page_url(link_header: str) -> str | None:
    """Parse the GitHub Link header for the next page URL."""
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    return match.group(1) if match else None


async def get_authenticated_user(token: str) -> dict[str, Any]:
    """
    Verify the PAT and return the authenticated user's profile.

    Tries GET /user first (works for classic PATs and fine-grained PATs with
    Account: Email read permission). If that returns 403/404 (fine-grained PATs
    without Account permission), falls back to GET /user/repos to confirm the
    token is valid and extracts the owner login from the first repo.

    Raises ValueError on a hard 401 (bad/expired token).
    """
    client = _get_client()
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
    Auto-paginates up to per_page items.
    """
    page_size = min(per_page, 100)
    client = _get_client()
    all_repos: list[dict[str, Any]] = []
    url: str | None = f"{_BASE}/user/repos"
    params: dict[str, Any] = {"type": "all", "sort": "pushed", "per_page": page_size}
    while url and len(all_repos) < per_page:
        resp = await client.get(url, headers=_headers(token), params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            all_repos.extend(r for r in data if isinstance(r, dict))
        url = _next_page_url(resp.headers.get("link", ""))
        params = {}  # URL already contains params on subsequent pages
    return all_repos[:per_page]


async def get_pull_requests(
    token: str,
    owner: str,
    repo: str,
    state: str = "open",
    per_page: int = 30,
) -> list[dict[str, Any]]:
    """Return pull requests for a repository with auto-pagination."""
    page_size = min(per_page, 100)
    client = _get_client()
    all_prs: list[dict[str, Any]] = []
    url: str | None = f"{_BASE}/repos/{owner}/{repo}/pulls"
    params: dict[str, Any] = {"state": state, "per_page": page_size, "sort": "updated"}
    while url and len(all_prs) < per_page:
        resp = await client.get(url, headers=_headers(token), params=params)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            all_prs.extend(pr for pr in data if isinstance(pr, dict))
        url = _next_page_url(resp.headers.get("link", ""))
        params = {}
    return all_prs[:per_page]


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
    client = _get_client()
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
    client = _get_client()
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
    Return issues for a repository with auto-pagination.
    Pass labels="bug" to filter by label.
    GitHub issues API also returns PRs — filter them out with pull_request key check.
    """
    page_size = min(per_page, 100)
    params: dict[str, Any] = {"state": state, "per_page": page_size, "sort": "updated"}
    if labels:
        params["labels"] = labels
    client = _get_client()
    all_issues: list[dict[str, Any]] = []
    url: str | None = f"{_BASE}/repos/{owner}/{repo}/issues"
    while url and len(all_issues) < per_page:
        resp = await client.get(url, headers=_headers(token), params=params)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            # Exclude pull requests (GitHub returns them in /issues too)
            all_issues.extend(
                i for i in data if isinstance(i, dict) and "pull_request" not in i
            )
        url = _next_page_url(resp.headers.get("link", ""))
        params = {}
    return all_issues[:per_page]
