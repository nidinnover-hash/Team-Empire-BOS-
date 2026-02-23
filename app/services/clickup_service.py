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
        # Collect all ClickUp tasks first
        all_cu_tasks: list[dict[str, Any]] = []
        while True:
            tasks = await get_tasks(api_token, team_id, page=page, include_closed=False)
            if not tasks:
                break
            all_cu_tasks.extend(tasks)
            if len(tasks) < 100:
                break
            page += 1

        # Parse external_ids and build lookup data
        parsed: list[dict[str, Any]] = []
        for cu_task in all_cu_tasks:
            external_id = str(cu_task.get("id", ""))
            if not external_id:
                continue
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
            parsed.append({
                "external_id": external_id, "title": title, "description": description,
                "priority": priority, "due_date": due_date, "is_done": is_done,
            })

        # Batch-load all existing ClickUp tasks for this org (single query)
        ext_ids = [p["external_id"] for p in parsed]
        existing_map: dict[str, Task] = {}
        if ext_ids:
            result = await db.execute(
                select(Task).where(
                    Task.organization_id == org_id,
                    Task.external_source == "clickup",
                    Task.external_id.in_(ext_ids),
                )
            )
            for task in result.scalars().all():
                existing_map[task.external_id] = task

        # Upsert with per-item error handling
        for p in parsed:
            try:
                existing = existing_map.get(p["external_id"])
                if existing:
                    existing.title = p["title"]
                    existing.description = p["description"]
                    existing.priority = p["priority"]
                    existing.due_date = p["due_date"]
                    existing.is_done = p["is_done"]
                    if p["is_done"] and not existing.completed_at:
                        existing.completed_at = datetime.now(timezone.utc)
                else:
                    task = Task(
                        organization_id=org_id,
                        title=p["title"],
                        description=p["description"],
                        priority=p["priority"],
                        category="business",
                        due_date=p["due_date"],
                        is_done=p["is_done"],
                        external_id=p["external_id"],
                        external_source="clickup",
                    )
                    db.add(task)
                synced += 1
            except Exception as exc:
                logger.warning("ClickUp upsert skipped %s: %s", p["external_id"], exc)
                continue

        await db.commit()

    except Exception as exc:
        logger.warning("ClickUp sync failed: %s", exc)
        await db.rollback()
        return {"synced": synced, "error": str(exc)}

    await integration_service.mark_sync_time(db, item)
    return {"synced": synced, "error": None}
