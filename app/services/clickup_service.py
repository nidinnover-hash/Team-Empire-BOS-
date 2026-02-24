"""
ClickUp Sync Service — fetch tasks from ClickUp and upsert into the local Task table.

Stores the personal API token in Integration.config_json["access_token"] so it is
automatically encrypted/decrypted by token_crypto.encrypt_config / decrypt_config.
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import run_with_retry
from app.core.config import settings
from app.core.tenant import require_org_id
from app.models.ceo_control import ClickUpFolder, ClickUpList, ClickUpSpace, ClickUpTaskSnapshot
from app.models.task import Task
from app.services import integration as integration_service
from app.tools.clickup import (
    get_authorized_user,
    get_folders,
    get_lists_for_folder,
    get_spaces,
    get_tasks,
    get_teams,
    parse_due_date,
    parse_priority,
)

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
    require_org_id(org_id)
    user_info = await run_with_retry(lambda: get_authorized_user(api_token))
    teams = await run_with_retry(lambda: get_teams(api_token))
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
    critical_synced = 0
    page = 0
    try:
        now = datetime.now(timezone.utc)
        critical_folder = settings.CLICKUP_CRITICAL_FOLDER_NAME.strip().lower()
        critical_tag = settings.CLICKUP_CEO_PRIORITY_TAG.strip().lower()

        spaces = await run_with_retry(lambda: get_spaces(api_token, team_id))
        await db.execute(delete(ClickUpSpace).where(ClickUpSpace.organization_id == org_id))
        await db.execute(delete(ClickUpFolder).where(ClickUpFolder.organization_id == org_id))
        await db.execute(delete(ClickUpList).where(ClickUpList.organization_id == org_id))
        await db.execute(delete(ClickUpTaskSnapshot).where(ClickUpTaskSnapshot.organization_id == org_id))

        critical_folder_ids: set[str] = set()
        for space in spaces:
            sid = str(space.get("id") or "")
            if not sid:
                continue
            db.add(
                ClickUpSpace(
                    organization_id=org_id,
                    external_id=sid,
                    name=str(space.get("name") or sid),
                    synced_at=now,
                )
            )
            async def _load_folders(space_id: str = sid) -> list[dict[str, Any]]:
                return await get_folders(api_token, space_id)

            folders = await run_with_retry(_load_folders)
            for folder in folders:
                fid = str(folder.get("id") or "")
                if not fid:
                    continue
                fname = str(folder.get("name") or fid)
                if fname.lower() == critical_folder:
                    critical_folder_ids.add(fid)
                db.add(
                    ClickUpFolder(
                        organization_id=org_id,
                        external_id=fid,
                        space_external_id=sid,
                        name=fname,
                        synced_at=now,
                    )
                )
                async def _load_lists(folder_ext_id: str = fid) -> list[dict[str, Any]]:
                    return await get_lists_for_folder(api_token, folder_ext_id)

                lists = await run_with_retry(_load_lists)
                for lst in lists:
                    lid = str(lst.get("id") or "")
                    if not lid:
                        continue
                    db.add(
                        ClickUpList(
                            organization_id=org_id,
                            external_id=lid,
                            folder_external_id=fid,
                            name=str(lst.get("name") or lid),
                            synced_at=now,
                        )
                    )

        # Collect all ClickUp tasks first
        all_cu_tasks: list[dict[str, Any]] = []
        while True:
            async def _load_tasks(p: int = page) -> list[dict[str, Any]]:
                return await get_tasks(api_token, team_id, page=p, include_closed=False)

            tasks = await run_with_retry(_load_tasks)
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
                "raw": cu_task,
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
                    # Skip overwrite if local task was edited after remote update
                    raw_item = p["raw"]
                    updated_ms = raw_item.get("date_updated")
                    updated_remote = None
                    if updated_ms:
                        try:
                            updated_remote = datetime.fromtimestamp(int(updated_ms) / 1000, tz=timezone.utc)
                        except Exception:
                            pass
                    if updated_remote and getattr(existing, "updated_at", None) and existing.updated_at > updated_remote:
                        continue
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
                raw = p["raw"]
                assignees = [str(a.get("username") or a.get("email") or "") for a in (raw.get("assignees") or []) if isinstance(a, dict)]
                tags = [str(t.get("name") or "") for t in (raw.get("tags") or []) if isinstance(t, dict)]
                list_id = str((raw.get("list") or {}).get("id", "")) if isinstance(raw.get("list"), dict) else None
                folder_id = str((raw.get("folder") or {}).get("id", "")) if isinstance(raw.get("folder"), dict) else None
                updated_remote = None
                updated_ms = raw.get("date_updated")
                if updated_ms:
                    try:
                        updated_remote = datetime.fromtimestamp(int(updated_ms) / 1000, tz=timezone.utc)
                    except Exception:
                        updated_remote = None

                db.add(
                    ClickUpTaskSnapshot(
                        organization_id=org_id,
                        external_id=p["external_id"],
                        name=p["title"],
                        status=str((raw.get("status") or {}).get("status", "")) if isinstance(raw.get("status"), dict) else "",
                        assignees=json.dumps([x for x in assignees if x]),
                        due_date=p["due_date"] and datetime.combine(p["due_date"], datetime.min.time(), tzinfo=timezone.utc),
                        priority=str((raw.get("priority") or {}).get("priority", "")) if isinstance(raw.get("priority"), dict) else None,
                        tags=json.dumps([x for x in tags if x]),
                        list_id=list_id,
                        folder_id=folder_id,
                        url=str(raw.get("url") or ""),
                        updated_at_remote=updated_remote,
                        synced_at=now,
                    )
                )

                is_critical = (folder_id and folder_id in critical_folder_ids) or (critical_tag in {t.lower() for t in tags})
                if is_critical:
                    critical_synced += 1
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
    return {"synced": synced, "critical_synced": critical_synced, "error": None}
