"""
ClickUp API v2 client — async httpx, no dependencies on app DB or settings.

All functions accept an `api_token` (ClickUp personal token, e.g. pk_XXXX_YYYY)
and return plain Python dicts / lists from the ClickUp REST API.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.clickup.com/api/v2"
_TIMEOUT = 20.0


def _headers(api_token: str) -> dict[str, str]:
    return {"Authorization": api_token, "Content-Type": "application/json"}


async def get_authorized_user(api_token: str) -> dict[str, Any]:
    """
    Verify the token and return the authorized ClickUp user info.
    Raises httpx.HTTPStatusError on auth failure.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/user", headers=_headers(api_token))
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return {}
        user = body.get("user")
        return user if isinstance(user, dict) else {}


async def get_teams(api_token: str) -> list[dict[str, Any]]:
    """Return all workspaces (teams) the token has access to."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/team", headers=_headers(api_token))
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return []
        teams = body.get("teams")
        if not isinstance(teams, list):
            return []
        return [t for t in teams if isinstance(t, dict)]


async def get_tasks(
    api_token: str,
    team_id: str,
    page: int = 0,
    include_closed: bool = False,
    assignee_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch tasks from a ClickUp workspace using the teamwide task endpoint.

    Returns a list of task dicts.  Pass page=0, 1, 2 … until you get an empty list.
    Each task dict includes: id, name, description, status, priority, due_date,
    list, space, assignees, url.
    """
    params: dict[str, Any] = {
        "page": page,
        "include_closed": str(include_closed).lower(),
        "subtasks": "true",
    }
    if assignee_ids:
        params["assignees[]"] = assignee_ids

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/team/{team_id}/task",
            headers=_headers(api_token),
            params=params,
        )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return []
        tasks = body.get("tasks")
        if not isinstance(tasks, list):
            return []
        return [t for t in tasks if isinstance(t, dict)]


async def get_spaces(api_token: str, team_id: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/team/{team_id}/space", headers=_headers(api_token))
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return []
        spaces = body.get("spaces")
        if not isinstance(spaces, list):
            return []
        return [s for s in spaces if isinstance(s, dict)]


async def get_folders(api_token: str, space_id: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/space/{space_id}/folder", headers=_headers(api_token))
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return []
        folders = body.get("folders")
        if not isinstance(folders, list):
            return []
        return [f for f in folders if isinstance(f, dict)]


async def get_lists_for_folder(api_token: str, folder_id: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/folder/{folder_id}/list", headers=_headers(api_token))
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return []
        lists = body.get("lists")
        if not isinstance(lists, list):
            return []
        return [x for x in lists if isinstance(x, dict)]


def parse_due_date(task: dict[str, Any]) -> str | None:
    """Extract a human-readable due date from a ClickUp task dict (millisecond epoch)."""
    raw = task.get("due_date")
    if not raw:
        return None
    try:
        ts = int(raw) / 1000
        return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


def parse_priority(task: dict[str, Any]) -> int:
    """Map ClickUp priority (1=urgent 2=high 3=normal 4=low) to local scale (4=urgent 3=high 2=medium 1=low)."""
    prio_map = {1: 4, 2: 3, 3: 2, 4: 1}
    raw = task.get("priority")
    if isinstance(raw, dict):
        raw = raw.get("id")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return 2
    if not isinstance(raw, int | str):
        return 2
    try:
        return prio_map.get(int(raw), 2)
    except (TypeError, ValueError):
        return 2
