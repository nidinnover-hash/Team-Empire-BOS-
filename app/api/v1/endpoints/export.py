"""Full data export for backup/compliance."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import (
    command as command_service,
    contact as contact_service,
    finance as finance_service,
    goal as goal_service,
    memory as memory_service,
    note as note_service,
    project as project_service,
    task as task_service,
)

router = APIRouter(prefix="/export", tags=["export"])


def _serialize(obj: object) -> dict:
    """Convert a SQLAlchemy model to a JSON-safe dict."""
    d: dict[str, Any] = {}
    table = getattr(obj, "__table__", None)
    if table is None:
        return d
    for col in table.columns:
        val = getattr(obj, col.name, None)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif val is not None and hasattr(val, "isoformat"):
            iso = getattr(val, "isoformat", None)
            if callable(iso):
                val = iso()
        d[col.name] = val
    return d


@router.get("")
async def export_all_data(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> JSONResponse:
    """
    Export all user data as JSON. CEO-only.
    Returns tasks, projects, goals, notes, contacts, commands, finance, and memory.
    """
    org_id = int(actor.get("org_id"))

    tasks = await task_service.list_tasks(db, limit=10000, organization_id=org_id)
    projects = await project_service.list_projects(db, limit=10000, organization_id=org_id)
    goals = await goal_service.list_goals(db, limit=10000, organization_id=org_id)
    notes = await note_service.list_notes(db, limit=10000, organization_id=org_id)
    contacts = await contact_service.list_contacts(db, limit=10000, organization_id=org_id)
    commands = await command_service.list_commands(db, limit=10000, organization_id=org_id)
    finance = await finance_service.get_summary(db, organization_id=org_id)
    profile_memory = await memory_service.get_profile_memory(db, organization_id=org_id)
    team_members = await memory_service.get_team_members(db, organization_id=org_id)

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": org_id,
        "tasks": [_serialize(t) for t in tasks],
        "projects": [_serialize(p) for p in projects],
        "goals": [_serialize(g) for g in goals],
        "notes": [_serialize(n) for n in notes],
        "contacts": [_serialize(c) for c in contacts],
        "commands": [_serialize(c) for c in commands],
        "finance": finance if isinstance(finance, dict) else {},
        "profile_memory": [_serialize(m) for m in profile_memory],
        "team_members": [_serialize(m) for m in team_members],
    }

    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="personal-clone-export-{datetime.now(timezone.utc).strftime("%Y%m%d")}.json"',
        },
    )
