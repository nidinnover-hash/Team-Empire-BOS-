import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalProgressUpdate, GoalStatusUpdate
from app.services.notification import create_notification

logger = logging.getLogger(__name__)


async def create_goal(
    db: AsyncSession, data: GoalCreate, organization_id: int
) -> Goal:
    goal = Goal(**data.model_dump(), organization_id=organization_id)
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    logger.info("goal created id=%d org=%d", goal.id, organization_id)
    return goal


async def list_goals(
    db: AsyncSession, organization_id: int, limit: int = 50, offset: int = 0
) -> list[Goal]:
    result = await db.execute(
        select(Goal)
        .where(Goal.organization_id == organization_id, Goal.is_deleted.is_(False))
        .order_by(Goal.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_goal_progress(
    db: AsyncSession,
    goal_id: int,
    data: GoalProgressUpdate,
    organization_id: int,
) -> Goal | None:
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.organization_id == organization_id)
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        return None
    was_completed = goal.status == "completed"
    goal.progress = data.progress
    if data.progress == 100:
        goal.status = "completed"
    if goal.status == "completed" and not was_completed:
        await db.flush()
        await create_notification(
            db,
            organization_id=organization_id,
            type="goal_completed",
            severity="info",
            title=f"Goal Completed: {goal.title}",
            message=f"Goal \"{goal.title}\" reached 100% and is complete.",
            source="goals",
            entity_type="goal",
            entity_id=goal.id,
        )
    await db.commit()
    await db.refresh(goal)
    return goal


async def update_goal_status(
    db: AsyncSession,
    goal_id: int,
    data: GoalStatusUpdate,
    organization_id: int,
) -> Goal | None:
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.organization_id == organization_id)
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        return None
    goal.status = data.status
    await db.commit()
    await db.refresh(goal)
    return goal


async def get_goal(
    db: AsyncSession, goal_id: int, organization_id: int,
) -> Goal | None:
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.organization_id == organization_id, Goal.is_deleted.is_(False))
    )
    return result.scalar_one_or_none()


async def delete_goal(
    db: AsyncSession, goal_id: int, organization_id: int,
) -> bool:
    goal = await get_goal(db, goal_id, organization_id)
    if goal is None or goal.is_deleted:
        return False
    from datetime import UTC
    from datetime import datetime as dt
    goal.is_deleted = True
    goal.deleted_at = dt.now(UTC)
    await db.commit()
    logger.info("goal soft-deleted id=%d org=%d", goal_id, organization_id)
    return True


# ── Cascading Logic ──────────────────────────────────────────────────────────

async def recalculate_goal_progress(
    db: AsyncSession, goal_id: int, organization_id: int,
) -> None:
    """Recalculate goal progress as the average progress of linked projects.

    Auto-completes the goal when all linked projects are completed.
    """
    from app.models.project import Project

    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.organization_id == organization_id)
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        return

    # Get all projects linked to this goal
    proj_result = await db.execute(
        select(
            func.count(Project.id).label("total"),
            func.avg(Project.progress).label("avg_progress"),
            func.count(Project.id).filter(Project.status == "completed").label("completed"),
        ).where(Project.goal_id == goal_id, Project.organization_id == organization_id)
    )
    row = proj_result.one()
    total = row.total or 0

    if total == 0:
        return  # No linked projects, don't touch goal progress

    was_completed = goal.status == "completed"
    new_progress = round(float(row.avg_progress or 0))
    goal.progress = min(new_progress, 100)

    # Auto-complete goal when all linked projects are completed
    if row.completed == total and goal.status == "active":
        goal.progress = 100
        goal.status = "completed"
        if not was_completed:
            await db.flush()
            await create_notification(
                db,
                organization_id=organization_id,
                type="goal_completed",
                severity="info",
                title=f"Goal Completed: {goal.title}",
                message=f"All {total} projects for \"{goal.title}\" are complete.",
                source="goals",
                entity_type="goal",
                entity_id=goal.id,
            )
    # Re-activate goal if a project is un-completed
    elif goal.progress < 100 and goal.status == "completed":
        goal.status = "active"

    await db.commit()
    logger.info(
        "Goal %d progress: %d%% (%d/%d projects completed)",
        goal_id, goal.progress, row.completed or 0, total,
    )
