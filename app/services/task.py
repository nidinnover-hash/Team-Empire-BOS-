import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.notification import create_notification

logger = logging.getLogger(__name__)


async def create_task(
    db: AsyncSession, data: TaskCreate, organization_id: int, workspace_id: int | None = None,
) -> Task:
    task = Task(**data.model_dump(), organization_id=organization_id, workspace_id=workspace_id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    # Recalculate project progress when adding a task to a project
    if task.project_id:
        await recalculate_project_progress(db, task.project_id, organization_id)
    return task


async def list_tasks(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    organization_id: int = 0,
    workspace_id: int | None = None,
    project_id: int | None = None,
    category: str | None = None,
    is_done: bool | None = None,
) -> list[Task]:
    query = select(Task).where(Task.organization_id == organization_id, Task.is_deleted.is_(False))
    if workspace_id is not None:
        query = query.where(Task.workspace_id == workspace_id)
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
    organization_id: int = 0,
    workspace_id: int | None = None,
) -> Task | None:
    query = select(Task).where(Task.id == task_id, Task.organization_id == organization_id, Task.is_deleted.is_(False))
    if workspace_id is not None:
        query = query.where(Task.workspace_id == workspace_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if task is None:
        return None

    # Apply all non-None fields from the update payload
    was_done = task.is_done
    old_project_id = task.project_id
    if data.is_done is not None:
        task.is_done = data.is_done
        task.completed_at = datetime.now(UTC) if data.is_done else None
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

    if task.is_done and not was_done:
        await db.flush()
        await create_notification(
            db,
            organization_id=organization_id,
            type="task_completed",
            severity="info",
            title=f"Task Done: {task.title}",
            message=f"Task \"{task.title}\" has been completed.",
            source="tasks",
            entity_type="task",
            entity_id=task.id,
        )
    await db.commit()
    await db.refresh(task)

    # Cascade: recalculate project progress when task completion changes
    done_changed = (data.is_done is not None and task.is_done != was_done)
    project_changed = (data.project_id is not None and task.project_id != old_project_id)
    if done_changed or project_changed:
        if task.project_id:
            await recalculate_project_progress(db, task.project_id, organization_id)
        # Also update old project if task moved between projects
        if project_changed and old_project_id:
            await recalculate_project_progress(db, old_project_id, organization_id)

    return task


async def delete_task(
    db: AsyncSession,
    task_id: int,
    organization_id: int,
    workspace_id: int | None = None,
) -> bool:
    """Soft-delete a task. Returns True if deleted, False if not found."""
    from datetime import UTC
    from datetime import datetime as dt
    query = select(Task).where(Task.id == task_id, Task.organization_id == organization_id, Task.is_deleted.is_(False))
    if workspace_id is not None:
        query = query.where(Task.workspace_id == workspace_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if task is None:
        return False
    project_id = task.project_id
    task.is_deleted = True
    task.deleted_at = dt.now(UTC)
    await db.commit()
    # Recalculate project progress after removing a task
    if project_id:
        await recalculate_project_progress(db, project_id, organization_id)
    return True


# ── Cascading Logic ──────────────────────────────────────────────────────────

async def recalculate_project_progress(
    db: AsyncSession, project_id: int, organization_id: int,
) -> None:
    """Recalculate project progress based on % of tasks completed.

    Cascades to project status (auto-complete when 100%) and then to goal
    progress if the project is linked to a goal.
    """
    from app.models.project import Project

    # Count total and done tasks for this project
    result = await db.execute(
        select(
            func.count(Task.id).label("total"),
            func.count(Task.id).filter(Task.is_done.is_(True)).label("done"),
        ).where(Task.project_id == project_id, Task.organization_id == organization_id, Task.is_deleted.is_(False))
    )
    row = result.one()
    total, done = row.total or 0, row.done or 0

    proj_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.organization_id == organization_id)
    )
    project = proj_result.scalar_one_or_none()
    if project is None:
        return

    new_progress = round((done / total) * 100) if total > 0 else 0
    project.progress = new_progress

    # Auto-complete project when all tasks are done
    if new_progress == 100 and total > 0 and project.status == "active":
        project.status = "completed"
        await db.flush()
        await create_notification(
            db,
            organization_id=organization_id,
            type="project_completed",
            severity="info",
            title=f"Project Complete: {project.title}",
            message=f"All {total} tasks in \"{project.title}\" are done.",
            source="projects",
            entity_type="project",
            entity_id=project.id,
        )
    # Re-activate project if tasks are undone
    elif new_progress < 100 and project.status == "completed":
        project.status = "active"

    await db.commit()

    # Cascade to goal if project is linked
    if project.goal_id:
        from app.services.goal import recalculate_goal_progress
        await recalculate_goal_progress(db, project.goal_id, organization_id)

    logger.info(
        "Project %d progress: %d%% (%d/%d tasks) status=%s",
        project_id, new_progress, done, total, project.status,
    )
