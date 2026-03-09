"""Full data export for backup/compliance — JSON and CSV formats."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import (
    command as command_service,
)
from app.services import (
    contact as contact_service,
)
from app.services import (
    deal as deal_service,
)
from app.services import (
    finance as finance_service,
)
from app.services import (
    goal as goal_service,
)
from app.services import (
    memory as memory_service,
)
from app.services import (
    note as note_service,
)
from app.services import (
    project as project_service,
)
from app.services import (
    task as task_service,
)

router = APIRouter(prefix="/export", tags=["export"])


_EXPORT_EXCLUDE = {
    "password_hash", "hashed_password", "config_json", "access_token",
    "refresh_token", "token", "secret", "api_key", "encrypted_config",
}


def _serialize(obj: object) -> dict:
    """Convert a SQLAlchemy model to a JSON-safe dict, excluding sensitive columns."""
    d: dict[str, Any] = {}
    table = getattr(obj, "__table__", None)
    if table is None:
        return d
    for col in table.columns:
        if col.name in _EXPORT_EXCLUDE:
            continue
        val = getattr(obj, col.name, None)
        if isinstance(val, Decimal):
            val = float(val)
        elif isinstance(val, datetime):
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
    org_id = int(actor["org_id"])

    tasks = await task_service.list_tasks(db, limit=settings.EXPORT_MAX_ROWS, organization_id=org_id)
    projects = await project_service.list_projects(db, limit=settings.EXPORT_MAX_ROWS, organization_id=org_id)
    goals = await goal_service.list_goals(db, limit=settings.EXPORT_MAX_ROWS, organization_id=org_id)
    notes = await note_service.list_notes(db, limit=settings.EXPORT_MAX_ROWS, organization_id=org_id)
    contacts = await contact_service.list_contacts(db, limit=settings.EXPORT_MAX_ROWS, organization_id=org_id)
    commands = await command_service.list_commands(db, limit=settings.EXPORT_MAX_ROWS, organization_id=org_id)
    finance = await finance_service.get_summary(db, organization_id=org_id)
    profile_memory = await memory_service.get_profile_memory(db, organization_id=org_id)
    team_members = await memory_service.get_team_members(db, organization_id=org_id)

    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
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
            "Content-Disposition": f'attachment; filename="nidin-bos-export-{datetime.now(UTC).strftime("%Y%m%d")}.json"',
        },
    )


def _rows_to_csv(rows: list[dict]) -> str:
    """Convert a list of dicts to a CSV string."""
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _csv_response(csv_text: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/deals")
async def export_deals(
    fmt: str = Query("json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    """Export all deals as JSON or CSV."""
    org_id = int(actor["org_id"])
    deals = await deal_service.list_deals(db, organization_id=org_id, limit=settings.EXPORT_MAX_ROWS)
    rows = [_serialize(d) for d in deals]

    if fmt == "csv":
        return _csv_response(_rows_to_csv(rows), f"deals-{datetime.now(UTC).strftime('%Y%m%d')}.csv")
    return JSONResponse(content={"exported_at": datetime.now(UTC).isoformat(), "deals": rows})


@router.get("/contacts")
async def export_contacts(
    fmt: str = Query("json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    """Export all contacts as JSON or CSV."""
    org_id = int(actor["org_id"])
    contacts = await contact_service.list_contacts(db, organization_id=org_id, limit=settings.EXPORT_MAX_ROWS)
    rows = [_serialize(c) for c in contacts]

    if fmt == "csv":
        return _csv_response(_rows_to_csv(rows), f"contacts-{datetime.now(UTC).strftime('%Y%m%d')}.csv")
    return JSONResponse(content={"exported_at": datetime.now(UTC).isoformat(), "contacts": rows})


@router.get("/finance")
async def export_finance(
    fmt: str = Query("json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    """Export all finance entries as JSON or CSV."""
    org_id = int(actor["org_id"])
    entries = await finance_service.list_entries(db, organization_id=org_id, limit=settings.EXPORT_MAX_ROWS)
    rows = [_serialize(e) for e in entries]

    if fmt == "csv":
        return _csv_response(_rows_to_csv(rows), f"finance-{datetime.now(UTC).strftime('%Y%m%d')}.csv")
    return JSONResponse(content={"exported_at": datetime.now(UTC).isoformat(), "finance": rows})
