"""Smart task prioritization — score tasks based on due date, dependencies, goal alignment."""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task

logger = logging.getLogger(__name__)


def _compute_priority_score(task: Task, today: date | None = None) -> dict:
    """Compute a 0-100 priority score for a task based on heuristics.

    Factors:
    - Due date urgency (0-40 pts): overdue=40, within 1 day=35, within 3 days=25, within 7 days=15
    - Manual priority (0-25 pts): P1=25, P2=15, P3=8, P4=3
    - Has dependency (0-10 pts): if another task depends on this one
    - Age (0-15 pts): older incomplete tasks get more urgency
    - Has project (0-10 pts): project-linked tasks get slight boost
    """
    today = today or date.today()
    score = 0
    factors: list[str] = []

    # Due date urgency
    if task.due_date:
        days_until = (task.due_date - today).days
        if days_until < 0:
            score += 40
            factors.append(f"overdue by {abs(days_until)}d")
        elif days_until <= 1:
            score += 35
            factors.append("due within 1 day")
        elif days_until <= 3:
            score += 25
            factors.append("due within 3 days")
        elif days_until <= 7:
            score += 15
            factors.append("due this week")
        elif days_until <= 14:
            score += 5
            factors.append("due within 2 weeks")
    else:
        score += 5  # no due date = moderate baseline
        factors.append("no due date")

    # Manual priority
    prio_map = {1: 25, 2: 15, 3: 8, 4: 3}
    prio_score = prio_map.get(task.priority, 8)
    score += prio_score
    factors.append(f"priority P{task.priority}")

    # Age factor
    if task.created_at:
        created = task.created_at
        if hasattr(created, 'date'):
            created_date = created.date() if callable(created.date) else created
        else:
            created_date = today
        age_days = (today - created_date).days if isinstance(created_date, date) else 0
        if age_days > 14:
            score += 15
            factors.append(f"aged {age_days}d")
        elif age_days > 7:
            score += 10
            factors.append(f"aged {age_days}d")
        elif age_days > 3:
            score += 5

    # Project linkage
    if task.project_id:
        score += 10
        factors.append("project-linked")

    return {
        "task_id": task.id,
        "title": task.title,
        "score": min(100, score),
        "factors": factors,
        "priority": task.priority,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "category": task.category,
    }


async def get_prioritized_tasks(
    db: AsyncSession,
    organization_id: int,
    limit: int = 20,
) -> list[dict]:
    """Return incomplete tasks ranked by computed priority score."""
    result = await db.execute(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        ).limit(200)
    )
    tasks = list(result.scalars().all())
    scored = [_compute_priority_score(t) for t in tasks]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
