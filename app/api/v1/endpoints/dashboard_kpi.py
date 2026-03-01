"""Lightweight dashboard KPI polling endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import task as task_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/kpis")
async def get_dashboard_kpis(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    org_id = int(user["org_id"])
    tasks = await task_service.list_tasks(db, limit=200, is_done=False, organization_id=org_id)
    return {
        "tasks_pending": len(tasks) if tasks else 0,
    }
