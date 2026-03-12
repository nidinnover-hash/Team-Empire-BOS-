"""User activity heatmap service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_activity_heatmap import UserActivityEntry


async def record_activity(
    db: AsyncSession, *, organization_id: int, user_id: int,
    activity_type: str, hour_of_day: int, day_of_week: int,
    feature_name: str | None = None,
) -> UserActivityEntry:
    row = UserActivityEntry(
        organization_id=organization_id, user_id=user_id,
        activity_type=activity_type, hour_of_day=hour_of_day,
        day_of_week=day_of_week, feature_name=feature_name,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_activities(
    db: AsyncSession, organization_id: int, *,
    user_id: int | None = None, activity_type: str | None = None, limit: int = 100,
) -> list[UserActivityEntry]:
    q = select(UserActivityEntry).where(UserActivityEntry.organization_id == organization_id)
    if user_id is not None:
        q = q.where(UserActivityEntry.user_id == user_id)
    if activity_type:
        q = q.where(UserActivityEntry.activity_type == activity_type)
    q = q.order_by(UserActivityEntry.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_heatmap(db: AsyncSession, organization_id: int, *, user_id: int | None = None) -> dict:
    q = (
        select(
            UserActivityEntry.hour_of_day,
            UserActivityEntry.day_of_week,
            func.count(UserActivityEntry.id),
        )
        .where(UserActivityEntry.organization_id == organization_id)
        .group_by(UserActivityEntry.hour_of_day, UserActivityEntry.day_of_week)
    )
    if user_id is not None:
        q = q.where(UserActivityEntry.user_id == user_id)
    rows = (await db.execute(q)).all()
    # Build 7x24 grid
    grid = {d: {h: 0 for h in range(24)} for d in range(7)}
    for hour, day, count in rows:
        grid[day][hour] = count
    return grid


async def get_top_features(db: AsyncSession, organization_id: int, *, limit: int = 10) -> list[dict]:
    q = (
        select(UserActivityEntry.feature_name, func.count(UserActivityEntry.id).label("count"))
        .where(
            UserActivityEntry.organization_id == organization_id,
            UserActivityEntry.feature_name.isnot(None),
        )
        .group_by(UserActivityEntry.feature_name)
        .order_by(func.count(UserActivityEntry.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    return [{"feature": name, "count": count} for name, count in rows]
