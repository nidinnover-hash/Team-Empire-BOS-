from typing import cast

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


async def create_task(
    db: AsyncSession, data: TaskCreate, organization_id: int = 1
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

    task.is_done = data.is_done
    task.completed_at = datetime.now(timezone.utc) if data.is_done else None

    await db.commit()
    await db.refresh(task)
    return task
