from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_run import DailyRun


async def get_daily_run_by_scope(
    db: AsyncSession,
    organization_id: int,
    run_date: date,
    team_filter: str,
) -> DailyRun | None:
    result = await db.execute(
        select(DailyRun).where(
            DailyRun.organization_id == organization_id,
            DailyRun.run_date == run_date,
            DailyRun.team_filter == team_filter,
        )
    )
    return cast(DailyRun | None, result.scalar_one_or_none())


async def create_daily_run(
    db: AsyncSession,
    organization_id: int,
    run_date: date,
    team_filter: str,
    requested_by: int,
    status: str = "running",
) -> DailyRun:
    run = DailyRun(
        organization_id=organization_id,
        run_date=run_date,
        team_filter=team_filter,
        requested_by=requested_by,
        status=status,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def complete_daily_run(
    db: AsyncSession,
    run_id: int,
    organization_id: int,
    status: str,
    drafted_plan_count: int,
    drafted_email_count: int,
    pending_approvals: int,
    result_json: dict,
) -> DailyRun | None:
    result = await db.execute(
        select(DailyRun).where(
            DailyRun.id == run_id,
            DailyRun.organization_id == organization_id,
        )
    )
    run = cast(DailyRun | None, result.scalar_one_or_none())
    if run is None:
        return None
    run.status = status
    run.drafted_plan_count = drafted_plan_count
    run.drafted_email_count = drafted_email_count
    run.pending_approvals = pending_approvals
    run.result_json = result_json
    run.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(run)
    return run


async def list_daily_runs(
    db: AsyncSession,
    organization_id: int,
    run_date: date | None = None,
    limit: int = 30,
) -> list[DailyRun]:
    query = select(DailyRun).where(DailyRun.organization_id == organization_id)
    if run_date is not None:
        query = query.where(DailyRun.run_date == run_date)
    query = query.order_by(DailyRun.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
