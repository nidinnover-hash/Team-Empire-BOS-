"""Sales leaderboard service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales_leaderboard import LeaderboardEntry


async def upsert_entry(
    db: AsyncSession, *, organization_id: int, user_id: int,
    period: str, period_type: str = "monthly",
    total_revenue: float = 0, deals_closed: int = 0,
    deals_created: int = 0, activities_count: int = 0,
) -> LeaderboardEntry:
    q = select(LeaderboardEntry).where(
        LeaderboardEntry.organization_id == organization_id,
        LeaderboardEntry.user_id == user_id,
        LeaderboardEntry.period == period,
        LeaderboardEntry.period_type == period_type,
    )
    row = (await db.execute(q)).scalar_one_or_none()
    if row:
        row.total_revenue = total_revenue
        row.deals_closed = deals_closed
        row.deals_created = deals_created
        row.activities_count = activities_count
    else:
        row = LeaderboardEntry(
            organization_id=organization_id, user_id=user_id,
            period=period, period_type=period_type,
            total_revenue=total_revenue, deals_closed=deals_closed,
            deals_created=deals_created, activities_count=activities_count,
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_leaderboard(
    db: AsyncSession, organization_id: int, *,
    period: str, period_type: str = "monthly",
    sort_by: str = "total_revenue",
) -> list[LeaderboardEntry]:
    q = select(LeaderboardEntry).where(
        LeaderboardEntry.organization_id == organization_id,
        LeaderboardEntry.period == period,
        LeaderboardEntry.period_type == period_type,
    )
    col = getattr(LeaderboardEntry, sort_by, LeaderboardEntry.total_revenue)
    q = q.order_by(col.desc())
    return list((await db.execute(q)).scalars().all())


async def get_user_history(
    db: AsyncSession, organization_id: int, user_id: int,
    *, period_type: str = "monthly", limit: int = 12,
) -> list[LeaderboardEntry]:
    q = (
        select(LeaderboardEntry)
        .where(LeaderboardEntry.organization_id == organization_id, LeaderboardEntry.user_id == user_id, LeaderboardEntry.period_type == period_type)
        .order_by(LeaderboardEntry.period.desc())
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())
