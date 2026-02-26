from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution


async def create_execution(
    db: AsyncSession,
    organization_id: int,
    approval_id: int,
    triggered_by: int,
    status: str = "running",
) -> Execution:
    execution = Execution(
        organization_id=organization_id,
        approval_id=approval_id,
        triggered_by=triggered_by,
        status=status,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def complete_execution(
    db: AsyncSession,
    execution_id: int,
    status: str,
    output_json: dict | None = None,
    error_text: str | None = None,
    organization_id: int | None = None,
) -> Execution | None:
    query = select(Execution).where(Execution.id == execution_id)
    if organization_id is not None:
        query = query.where(Execution.organization_id == organization_id)
    result = await db.execute(query)
    execution = cast(Execution | None, result.scalar_one_or_none())
    if execution is None:
        return None
    execution.status = status
    execution.output_json = output_json or {}
    execution.error_text = error_text
    execution.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(execution)
    return execution


async def list_executions(
    db: AsyncSession,
    organization_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list[Execution]:
    query = select(Execution).where(Execution.organization_id == organization_id)
    if status is not None:
        query = query.where(Execution.status == status)
    query = query.order_by(Execution.started_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
