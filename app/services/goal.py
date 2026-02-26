from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalProgressUpdate, GoalStatusUpdate


async def create_goal(
    db: AsyncSession, data: GoalCreate, organization_id: int
) -> Goal:
    goal = Goal(**data.model_dump(), organization_id=organization_id)
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


async def list_goals(
    db: AsyncSession, organization_id: int, limit: int = 50
) -> list[Goal]:
    result = await db.execute(
        select(Goal)
        .where(Goal.organization_id == organization_id)
        .order_by(Goal.created_at.desc())
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
    goal = cast(Goal | None, result.scalar_one_or_none())
    if goal is None:
        return None
    goal.progress = data.progress
    if data.progress == 100:
        goal.status = "completed"
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
    goal = cast(Goal | None, result.scalar_one_or_none())
    if goal is None:
        return None
    goal.status = data.status
    await db.commit()
    await db.refresh(goal)
    return goal
