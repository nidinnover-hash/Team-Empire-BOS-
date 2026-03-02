import logging

from sqlalchemy import select
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
        .where(Goal.organization_id == organization_id)
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
        select(Goal).where(Goal.id == goal_id, Goal.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def delete_goal(
    db: AsyncSession, goal_id: int, organization_id: int,
) -> bool:
    goal = await get_goal(db, goal_id, organization_id)
    if goal is None:
        return False
    await db.delete(goal)
    await db.commit()
    logger.info("goal deleted id=%d org=%d", goal_id, organization_id)
    return True
