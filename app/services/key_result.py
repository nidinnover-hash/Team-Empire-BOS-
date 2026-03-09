"""Key Result service — CRUD for OKR key results linked to goals."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.key_result import KeyResult

logger = logging.getLogger(__name__)


async def create_key_result(
    db: AsyncSession,
    organization_id: int,
    goal_id: int,
    title: str,
    *,
    description: str | None = None,
    metric_unit: str | None = None,
    target_value: float = 100.0,
    current_value: float = 0.0,
) -> KeyResult:
    progress = int(min(100, max(0, (current_value / target_value) * 100))) if target_value else 0
    kr = KeyResult(
        organization_id=organization_id,
        goal_id=goal_id,
        title=title,
        description=description,
        metric_unit=metric_unit,
        target_value=target_value,
        current_value=current_value,
        progress=progress,
    )
    db.add(kr)
    await db.commit()
    await db.refresh(kr)
    return kr


async def list_key_results(
    db: AsyncSession,
    organization_id: int,
    goal_id: int,
) -> list[KeyResult]:
    result = await db.execute(
        select(KeyResult).where(
            KeyResult.organization_id == organization_id,
            KeyResult.goal_id == goal_id,
        ).order_by(KeyResult.created_at)
    )
    return list(result.scalars().all())


async def update_key_result(
    db: AsyncSession,
    organization_id: int,
    kr_id: int,
    *,
    current_value: float | None = None,
    title: str | None = None,
    status: str | None = None,
) -> KeyResult | None:
    result = await db.execute(
        select(KeyResult).where(
            KeyResult.id == kr_id,
            KeyResult.organization_id == organization_id,
        )
    )
    kr = result.scalar_one_or_none()
    if kr is None:
        return None

    if title is not None:
        kr.title = title
    if current_value is not None:
        kr.current_value = current_value
        kr.progress = int(min(100, max(0, (current_value / kr.target_value) * 100))) if kr.target_value else 0
        if kr.progress >= 100:
            kr.status = "completed"
    if status is not None:
        kr.status = status

    kr.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(kr)
    return kr


async def delete_key_result(
    db: AsyncSession,
    organization_id: int,
    kr_id: int,
) -> bool:
    result = await db.execute(
        select(KeyResult).where(
            KeyResult.id == kr_id,
            KeyResult.organization_id == organization_id,
        )
    )
    kr = result.scalar_one_or_none()
    if kr is None:
        return False
    await db.delete(kr)
    await db.commit()
    return True


async def recalculate_goal_progress(
    db: AsyncSession,
    organization_id: int,
    goal_id: int,
) -> int:
    """Recalculate goal progress as average of its key results. Returns new progress."""
    result = await db.execute(
        select(func.avg(KeyResult.progress)).where(
            KeyResult.organization_id == organization_id,
            KeyResult.goal_id == goal_id,
            KeyResult.status != "abandoned",
        )
    )
    avg = result.scalar()
    return int(avg or 0)
