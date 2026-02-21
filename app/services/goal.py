from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalProgressUpdate, GoalStatusUpdate


async def create_goal(db: AsyncSession, data: GoalCreate) -> Goal:
    goal = Goal(**data.model_dump())
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


async def list_goals(db: AsyncSession, limit: int = 50) -> list[Goal]:
    result = await db.execute(
        select(Goal).order_by(Goal.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def update_goal_progress(
    db: AsyncSession, goal_id: int, data: GoalProgressUpdate
) -> Goal | None:
    result = await db.execute(select(Goal).where(Goal.id == goal_id))
    goal = result.scalar_one_or_none()
    if goal is None:
        return None
    goal.progress = data.progress
    if data.progress == 100:
        goal.status = "completed"
    await db.commit()
    await db.refresh(goal)
    return goal


async def update_goal_status(
    db: AsyncSession, goal_id: int, data: GoalStatusUpdate
) -> Goal | None:
    result = await db.execute(select(Goal).where(Goal.id == goal_id))
    goal = result.scalar_one_or_none()
    if goal is None:
        return None
    goal.status = data.status
    await db.commit()
    await db.refresh(goal)
    return goal
