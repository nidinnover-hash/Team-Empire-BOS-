from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution


async def create_execution(
    db: AsyncSession,
    organization_id: int,
    approval_id: int,
    triggered_by: int,
    status: str = "running",
    execute_idempotency_key: str | None = None,
) -> tuple[Execution, bool]:
    execution = Execution(
        organization_id=organization_id,
        approval_id=approval_id,
        triggered_by=triggered_by,
        status=status,
        execute_idempotency_key=execute_idempotency_key,
    )
    try:
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution, True
    except IntegrityError:
        await db.rollback()
        if execute_idempotency_key:
            existing_by_key = (
                await db.execute(
                    select(Execution).where(
                        Execution.organization_id == organization_id,
                        Execution.execute_idempotency_key == execute_idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing_by_key is not None:
                return existing_by_key, False
        existing = (
            await db.execute(
                select(Execution).where(Execution.approval_id == approval_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing, False


async def get_execution_by_idempotency_key(
    db: AsyncSession,
    *,
    organization_id: int,
    execute_idempotency_key: str,
) -> Execution | None:
    result = await db.execute(
        select(Execution).where(
            Execution.organization_id == organization_id,
            Execution.execute_idempotency_key == execute_idempotency_key,
        )
    )
    return result.scalar_one_or_none()


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
    execution = result.scalar_one_or_none()
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
