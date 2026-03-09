"""Task template service — CRUD and generation of recurring tasks."""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_template import TaskTemplate

logger = logging.getLogger(__name__)


async def create_template(
    db: AsyncSession,
    organization_id: int,
    title: str,
    *,
    description: str | None = None,
    priority: int = 2,
    category: str = "personal",
    project_id: int | None = None,
    recurrence: str = "weekly",
    recurrence_detail: str | None = None,
) -> TaskTemplate:
    tmpl = TaskTemplate(
        organization_id=organization_id,
        title=title,
        description=description,
        priority=priority,
        category=category,
        project_id=project_id,
        recurrence=recurrence,
        recurrence_detail=recurrence_detail,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


async def list_templates(
    db: AsyncSession,
    organization_id: int,
    active_only: bool = True,
) -> list[TaskTemplate]:
    q = select(TaskTemplate).where(TaskTemplate.organization_id == organization_id)
    if active_only:
        q = q.where(TaskTemplate.is_active.is_(True))
    q = q.order_by(TaskTemplate.created_at.desc())
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_template(
    db: AsyncSession,
    organization_id: int,
    template_id: int,
    **kwargs,
) -> TaskTemplate | None:
    result = await db.execute(
        select(TaskTemplate).where(
            TaskTemplate.id == template_id,
            TaskTemplate.organization_id == organization_id,
        )
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        return None

    for key, val in kwargs.items():
        if val is not None and hasattr(tmpl, key):
            setattr(tmpl, key, val)

    tmpl.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


async def delete_template(
    db: AsyncSession,
    organization_id: int,
    template_id: int,
) -> bool:
    result = await db.execute(
        select(TaskTemplate).where(
            TaskTemplate.id == template_id,
            TaskTemplate.organization_id == organization_id,
        )
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        return False
    await db.delete(tmpl)
    await db.commit()
    return True


def _should_generate(tmpl: TaskTemplate, today: date) -> bool:
    """Check if a template should generate a task today."""
    if tmpl.last_generated_at:
        last_date = tmpl.last_generated_at.date() if isinstance(tmpl.last_generated_at, datetime) else tmpl.last_generated_at
        if last_date >= today:
            return False

    recurrence = (tmpl.recurrence or "weekly").lower()
    if recurrence == "daily":
        return True
    elif recurrence == "weekly":
        detail = tmpl.recurrence_detail or "0"  # default Monday
        days = [int(d.strip()) for d in detail.split(",") if d.strip().isdigit()]
        return today.weekday() in days
    elif recurrence == "monthly":
        detail = tmpl.recurrence_detail or "1"
        day = int(detail.strip()) if detail.strip().isdigit() else 1
        return today.day == day
    return False


async def generate_due_tasks(
    db: AsyncSession,
    organization_id: int,
) -> int:
    """Generate tasks from active templates that are due today. Returns count created."""
    today = date.today()
    templates = await list_templates(db, organization_id, active_only=True)
    created = 0

    for tmpl in templates:
        if not _should_generate(tmpl, today):
            continue

        # Calculate due date
        if tmpl.recurrence == "daily":
            due = today
        elif tmpl.recurrence == "weekly":
            due = today + timedelta(days=7)
        else:
            due = today + timedelta(days=30)

        task = Task(
            organization_id=organization_id,
            title=tmpl.title,
            description=tmpl.description,
            priority=tmpl.priority,
            category=tmpl.category,
            project_id=tmpl.project_id,
            due_date=due,
        )
        db.add(task)
        tmpl.last_generated_at = datetime.now(UTC)
        created += 1

    if created:
        await db.commit()
    logger.info("Generated %d recurring tasks for org=%d", created, organization_id)
    return created
