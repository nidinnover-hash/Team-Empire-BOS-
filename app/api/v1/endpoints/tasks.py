from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_workspace_id, get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import task as task_service
from app.services import task_priority as priority_service
from app.services import task_template as template_service


class TaskTemplateCreate(BaseModel):
    title: str = Field(..., max_length=500)
    description: str | None = None
    priority: int = Field(2, ge=1, le=4)
    category: str = "personal"
    project_id: int | None = None
    recurrence: str = Field("weekly", pattern=r"^(daily|weekly|monthly)$")
    recurrence_detail: str | None = Field(None, max_length=100)


class TaskTemplateUpdate(BaseModel):
    title: str | None = Field(None, max_length=500)
    description: str | None = None
    priority: int | None = Field(None, ge=1, le=4)
    recurrence: str | None = Field(None, pattern=r"^(daily|weekly|monthly)$")
    recurrence_detail: str | None = None
    is_active: bool | None = None


class TaskTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    priority: int
    category: str
    project_id: int | None = None
    recurrence: str
    recurrence_detail: str | None = None
    is_active: bool
    last_generated_at: datetime | None = None
    created_at: datetime | None = None

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> TaskRead:
    """Create a task. Optionally link to a project and set priority/due_date."""
    task = await task_service.create_task(
        db,
        data,
        organization_id=actor["org_id"],
        workspace_id=workspace_id,
    )
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
    workspace_id: int = Depends(get_current_workspace_id),
    project_id: int | None = Query(None, description="Filter by project"),
    category: str | None = Query(None, description="personal|business|health|finance|other", max_length=50),
    is_done: bool | None = Query(None, description="true=done, false=open"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
) -> list[TaskRead]:
    """List tasks. Filter by project, category, or status. Sorted by priority."""
    return await task_service.list_tasks(
        db, organization_id=actor["org_id"], project_id=project_id,
        category=category, is_done=is_done, limit=limit, offset=offset,
        workspace_id=workspace_id,
    )


@router.get("/prioritized")
async def get_prioritized_tasks(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[dict]:
    """Return incomplete tasks ranked by computed priority score."""
    return await priority_service.get_prioritized_tasks(db, organization_id=actor["org_id"], limit=limit)


@router.get("/templates", response_model=list[TaskTemplateRead])
async def list_task_templates(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[TaskTemplateRead]:
    """List recurring task templates."""
    items = await template_service.list_templates(db, organization_id=actor["org_id"], active_only=active_only)
    return [TaskTemplateRead.model_validate(t, from_attributes=True) for t in items]


@router.post("/templates", response_model=TaskTemplateRead, status_code=201)
async def create_task_template(
    data: TaskTemplateCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> TaskTemplateRead:
    """Create a recurring task template."""
    tmpl = await template_service.create_template(
        db, organization_id=actor["org_id"],
        title=data.title, description=data.description,
        priority=data.priority, category=data.category,
        project_id=data.project_id, recurrence=data.recurrence,
        recurrence_detail=data.recurrence_detail,
    )
    await record_action(
        db, event_type="task_template_created", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="task_template", entity_id=tmpl.id,
        payload_json={"title": data.title, "recurrence": data.recurrence},
    )
    return TaskTemplateRead.model_validate(tmpl, from_attributes=True)


@router.patch("/templates/{template_id}", response_model=TaskTemplateRead)
async def update_task_template(
    template_id: int,
    data: TaskTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> TaskTemplateRead:
    """Update a recurring task template."""
    tmpl = await template_service.update_template(
        db, organization_id=actor["org_id"], template_id=template_id,
        **data.model_dump(exclude_unset=True),
    )
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Task template not found")
    return TaskTemplateRead.model_validate(tmpl, from_attributes=True)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_task_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await template_service.delete_template(db, organization_id=actor["org_id"], template_id=template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task template not found")


@router.post("/templates/generate")
async def generate_recurring_tasks(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Manually trigger generation of recurring tasks from templates."""
    count = await template_service.generate_due_tasks(db, organization_id=actor["org_id"])
    return {"generated": count}


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> TaskRead:
    """Update a task — edit fields, mark done, or reopen."""
    task = await task_service.update_task(
        db,
        task_id,
        data,
        organization_id=actor["org_id"],
        workspace_id=workspace_id,
    )
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
    workspace_id: int = Depends(get_current_workspace_id),
) -> None:
    """Delete a task. CEO/ADMIN only."""
    deleted = await task_service.delete_task(
        db,
        task_id,
        organization_id=actor["org_id"],
        workspace_id=workspace_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    await record_action(
        db, event_type="task_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="task", entity_id=task_id,
    )
