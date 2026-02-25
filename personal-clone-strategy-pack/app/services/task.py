from typing import cast

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


async def create_task(
    db: AsyncSession, data: TaskCreate, organization_id: int,
) -> Task:
    task = Task(**data.model_dump(), organization_id=organization_id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def list_tasks(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    organization_id: int | None = None,
    project_id: int | None = None,
    category: str | None = None,
    is_done: bool | None = None,
) -> list[Task]:
    query = select(Task)
    if organization_id is not None:
        query = query.where(Task.organization_id == organization_id)
    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    if category is not None:
        query = query.where(Task.category == category)
    if is_done is not None:
        query = query.where(Task.is_done == is_done)
    # Sort by priority desc (urgent first), then newest
    query = query.order_by(Task.priority.desc(), Task.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_task(
    db: AsyncSession,
    task_id: int,
    data: TaskUpdate,
    organization_id: int | None = None,
) -> Task | None:
    query = select(Task).where(Task.id == task_id)
    if organization_id is not None:
        query = query.where(Task.organization_id == organization_id)
    result = await db.execute(query)
    task = cast(Task | None, result.scalar_one_or_none())
    if task is None:
        return None

    # Apply all non-None fields from the update payload
    if data.is_done is not None:
        task.is_done = data.is_done
        task.completed_at = datetime.now(timezone.utc) if data.is_done else None
    if data.title is not None:
        task.title = data.title
    if data.description is not None:
        task.description = data.description
    if data.priority is not None:
        task.priority = data.priority
    if data.category is not None:
        task.category = data.category
    if data.project_id is not None:
        task.project_id = data.project_id
    if data.due_date is not None:
        task.due_date = data.due_date

    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(
    db: AsyncSession,
    task_id: int,
    organization_id: int,
) -> bool:
    """Delete a task. Returns True if deleted, False if not found."""
    query = select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if task is None:
        return False
    await db.delete(task)
    await db.commit()
    return True
