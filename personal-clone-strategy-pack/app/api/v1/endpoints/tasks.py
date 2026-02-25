from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.task import TaskCreate, TaskUpdate, TaskRead
from app.services import task as task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> TaskRead:
    """Create a task. Optionally link to a project and set priority/due_date."""
    task = await task_service.create_task(db, data, organization_id=actor["org_id"])
    await record_action(
        db, event_type="task_created", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="task", entity_id=task.id,
        payload_json={"title": task.title, "priority": task.priority},
    )
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    project_id: int | None = Query(None, description="Filter by project"),
    category: str | None = Query(None, description="personal|business|health|finance|other"),
    is_done: bool | None = Query(None, description="true=done, false=open"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[TaskRead]:
    """List tasks. Filter by project, category, or status. Sorted by priority."""
    return await task_service.list_tasks(
        db, organization_id=actor["org_id"], project_id=project_id,
        category=category, is_done=is_done, limit=limit, offset=offset,
    )


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> TaskRead:
    """Update a task — edit fields, mark done, or reopen."""
    task = await task_service.update_task(db, task_id, data, organization_id=actor["org_id"])
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await record_action(
        db, event_type="task_updated", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="task", entity_id=task_id,
        payload_json=data.model_dump(exclude_unset=True),
    )
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    """Delete a task. CEO/ADMIN only."""
    deleted = await task_service.delete_task(db, task_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    await record_action(
        db, event_type="task_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="task", entity_id=task_id,
    )
