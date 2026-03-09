"""Report schedule service — CRUD and generation for recurring reports."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_schedule import ReportSchedule

logger = logging.getLogger(__name__)

REPORT_TYPES = ("kpi_summary", "deal_pipeline", "task_status", "finance_summary")
FREQUENCIES = ("daily", "weekly", "monthly")


async def create_schedule(
    db: AsyncSession, organization_id: int, created_by_user_id: int, **kwargs,
) -> ReportSchedule:
    if "recipients" in kwargs:
        kwargs["recipients_json"] = json.dumps(kwargs.pop("recipients"))
    schedule = ReportSchedule(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        **kwargs,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


async def list_schedules(
    db: AsyncSession, organization_id: int, active_only: bool = True,
) -> list[ReportSchedule]:
    q = select(ReportSchedule).where(
        ReportSchedule.organization_id == organization_id,
    )
    if active_only:
        q = q.where(ReportSchedule.is_active.is_(True))
    q = q.order_by(ReportSchedule.id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_schedule(
    db: AsyncSession, schedule_id: int, organization_id: int, **kwargs,
) -> ReportSchedule | None:
    result = await db.execute(
        select(ReportSchedule).where(
            ReportSchedule.id == schedule_id,
            ReportSchedule.organization_id == organization_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        return None
    if "recipients" in kwargs:
        kwargs["recipients_json"] = json.dumps(kwargs.pop("recipients"))
    for k, v in kwargs.items():
        if v is not None and hasattr(schedule, k):
            setattr(schedule, k, v)
    await db.commit()
    await db.refresh(schedule)
    return schedule


async def delete_schedule(
    db: AsyncSession, schedule_id: int, organization_id: int,
) -> bool:
    result = await db.execute(
        select(ReportSchedule).where(
            ReportSchedule.id == schedule_id,
            ReportSchedule.organization_id == organization_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        return False
    await db.delete(schedule)
    await db.commit()
    return True


async def get_schedule(
    db: AsyncSession, schedule_id: int, organization_id: int,
) -> ReportSchedule | None:
    result = await db.execute(
        select(ReportSchedule).where(
            ReportSchedule.id == schedule_id,
            ReportSchedule.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()
