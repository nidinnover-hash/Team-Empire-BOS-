from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.task import TaskCreate, TaskUpdate, TaskRead
from app.services import task as task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskRead:
    """Create a task. Optionally link to a project and set priority/due_date."""
    return await task_service.create_task(db, data)


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    project_id: int | None = Query(None, description="Filter by project"),
    category: str | None = Query(None, description="personal|business|health|finance|other"),
    is_done: bool | None = Query(None, description="true=done, false=open"),
) -> list[TaskRead]:
    """List tasks. Filter by project, category, or status. Sorted by priority."""
    return await task_service.list_tasks(
        db, project_id=project_id, category=category, is_done=is_done
    )


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
) -> TaskRead:
    """Mark a task done or reopen it."""
    task = await task_service.update_task(db, task_id, data)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task
