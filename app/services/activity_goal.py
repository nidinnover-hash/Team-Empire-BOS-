"""Activity goals / quotas service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_goal import ActivityGoal


async def create_goal(
    db: AsyncSession, *, organization_id: int, user_id: int,
    activity_type: str, period: str, period_type: str = "weekly",
    target: int = 0,
) -> ActivityGoal:
    row = ActivityGoal(
        organization_id=organization_id, user_id=user_id,
        activity_type=activity_type, period=period,
        period_type=period_type, target=target,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_goals(
    db: AsyncSession, organization_id: int, *,
    user_id: int | None = None, activity_type: str | None = None,
    period: str | None = None,
) -> list[ActivityGoal]:
    q = select(ActivityGoal).where(ActivityGoal.organization_id == organization_id)
    if user_id is not None:
        q = q.where(ActivityGoal.user_id == user_id)
    if activity_type:
        q = q.where(ActivityGoal.activity_type == activity_type)
    if period:
        q = q.where(ActivityGoal.period == period)
    q = q.order_by(ActivityGoal.activity_type)
    return list((await db.execute(q)).scalars().all())


async def get_goal(db: AsyncSession, goal_id: int, organization_id: int) -> ActivityGoal | None:
    q = select(ActivityGoal).where(ActivityGoal.id == goal_id, ActivityGoal.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def record_activity(
    db: AsyncSession, goal_id: int, organization_id: int, count: int = 1,
) -> ActivityGoal | None:
    row = await get_goal(db, goal_id, organization_id)
    if not row:
        return None
    row.current += count
    if row.current >= row.target:
        row.streak += 1
        if row.streak > row.best_streak:
            row.best_streak = row.streak
    await db.commit()
    await db.refresh(row)
    return row


async def reset_period(
    db: AsyncSession, goal_id: int, organization_id: int, new_period: str,
) -> ActivityGoal | None:
    row = await get_goal(db, goal_id, organization_id)
    if not row:
        return None
    if row.current < row.target:
        row.streak = 0
    row.current = 0
    row.period = new_period
    await db.commit()
    await db.refresh(row)
    return row


async def get_progress(db: AsyncSession, organization_id: int, user_id: int) -> list[dict]:
    goals = await list_goals(db, organization_id, user_id=user_id)
    return [
        {
            "id": g.id, "activity_type": g.activity_type,
            "period": g.period, "target": g.target,
            "current": g.current, "streak": g.streak,
            "best_streak": g.best_streak,
            "pct": round(g.current / g.target * 100, 1) if g.target > 0 else 0,
        }
        for g in goals
    ]
