"""
ClickUp Sync Service — fetch tasks from ClickUp and upsert into the local Task table.

Stores the personal API token in Integration.config_json["access_token"] so it is
automatically encrypted/decrypted by token_crypto.encrypt_config / decrypt_config.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.services import integration as integration_service
from app.tools.clickup import get_authorized_user, get_tasks, get_teams, parse_due_date, parse_priority

logger = logging.getLogger(__name__)

_CLICKUP_TYPE = "clickup"


async def get_clickup_status(db: AsyncSession, org_id: int) -> dict[str, Any]:
    """Return connection status for the ClickUp integration."""
    item = await integration_service.get_integration_by_type(db, org_id, _CLICKUP_TYPE)
    if item is None:
        return {"connected": False, "last_sync_at": None, "username": None, "team_id": None}
    cfg = item.config_json or {}
    return {
        "connected": item.status == "connected",
        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        "username": cfg.get("username"),
        "team_id": cfg.get("team_id"),
    }


async def connect_clickup(
    db: AsyncSession, org_id: int, api_token: str
) -> dict[str, Any]:
    """
    Verify the ClickUp personal token, then store it in the Integration table.
    Returns the integration info dict on success; raises on auth failure.
    """
    user_info = await get_authorized_user(api_token)
    teams = await get_teams(api_token)
    team_id = str(teams[0]["id"]) if teams else None

    config_json = {
        # Stored as access_token so encrypt_config() auto-encrypts it
        "access_token": api_token,
        "user_id": str(user_info.get("id", "")),
        "username": user_info.get("username", ""),
        "email": user_info.get("email", ""),
        "team_id": team_id,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }

    item = await integration_service.connect_integration(
        db,
        organization_id=org_id,
        integration_type=_CLICKUP_TYPE,
        config_json=config_json,
    )
    return {
        "id": item.id,
        "status": item.status,
        "username": config_json["username"],
        "team_id": team_id,
    }


async def sync_clickup_tasks(db: AsyncSession, org_id: int) -> dict[str, Any]:
    """
    Fetch all open tasks from ClickUp and upsert them into the local Task table.

    Uses external_id + external_source="clickup" for dedup — syncing twice is safe.
    Returns {"synced": N, "error": None} or {"synced": 0, "error": "<msg>"}.
    """
    item = await integration_service.get_integration_by_type(db, org_id, _CLICKUP_TYPE)
    if item is None or item.status != "connected":
        return {"synced": 0, "error": "ClickUp integration is not connected"}

    cfg = item.config_json or {}
    api_token = cfg.get("access_token")
    team_id = cfg.get("team_id")

    if not api_token or not team_id:
        return {"synced": 0, "error": "Missing access_token or team_id in ClickUp config"}

    synced = 0
    page = 0
    try:
        while True:
            tasks = await get_tasks(api_token, team_id, page=page, include_closed=False)
            if not tasks:
                break
            for t in tasks:
                await _upsert_task(db, org_id, t)
                synced += 1
            if len(tasks) < 100:
                # ClickUp returns up to 100 per page; fewer means last page
                break
            page += 1
    except Exception as exc:
        logger.warning("ClickUp sync failed: %s", exc)
        return {"synced": synced, "error": str(exc)}

    await integration_service.mark_sync_time(db, item)
    return {"synced": synced, "error": None}


async def _upsert_task(db: AsyncSession, org_id: int, cu_task: dict[str, Any]) -> None:
    """Insert or update a single ClickUp task in the local Task table."""
    external_id = str(cu_task.get("id", ""))
    if not external_id:
        return

    result = await db.execute(
        select(Task).where(
            Task.organization_id == org_id,
            Task.external_source == "clickup",
            Task.external_id == external_id,
        )
    )
    existing = result.scalar_one_or_none()

    status_name = ""
    status_obj = cu_task.get("status")
    if isinstance(status_obj, dict):
        status_name = status_obj.get("status", "").lower()
    is_done = status_name in ("complete", "done", "closed")

    title = (cu_task.get("name") or "Untitled")[:500]
    description = cu_task.get("description") or None
    priority = parse_priority(cu_task)
    due_date_str = parse_due_date(cu_task)
    due_date = None
    if due_date_str:
        from datetime import date
        try:
            due_date = date.fromisoformat(due_date_str)
        except Exception:
            pass

    if existing:
        existing.title = title
        existing.description = description
        existing.priority = priority
        existing.due_date = due_date
        existing.is_done = is_done
        if is_done and not existing.completed_at:
            existing.completed_at = datetime.now(timezone.utc)
    else:
        task = Task(
            organization_id=org_id,
            title=title,
            description=description,
            priority=priority,
            category="business",
            due_date=due_date,
            is_done=is_done,
            external_id=external_id,
            external_source="clickup",
        )
        db.add(task)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
