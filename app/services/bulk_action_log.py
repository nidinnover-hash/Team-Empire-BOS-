"""Bulk action audit trail service — log and query bulk operations."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bulk_action_log import BulkActionLog


async def log_bulk_action(
    db: AsyncSession, organization_id: int, user_id: int,
    action_type: str, entity_type: str,
    total_records: int, success_count: int, failure_count: int,
    details: dict | None = None, rollback_data: dict | None = None,
    status: str = "completed",
) -> BulkActionLog:
    log = BulkActionLog(
        organization_id=organization_id, user_id=user_id,
        action_type=action_type, entity_type=entity_type,
        total_records=total_records, success_count=success_count,
        failure_count=failure_count, status=status,
        details_json=json.dumps(details) if details else None,
        rollback_data_json=json.dumps(rollback_data) if rollback_data else None,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def list_bulk_actions(
    db: AsyncSession, organization_id: int,
    action_type: str | None = None, entity_type: str | None = None,
    limit: int = 50,
) -> list[BulkActionLog]:
    q = select(BulkActionLog).where(BulkActionLog.organization_id == organization_id)
    if action_type:
        q = q.where(BulkActionLog.action_type == action_type)
    if entity_type:
        q = q.where(BulkActionLog.entity_type == entity_type)
    result = await db.execute(q.order_by(BulkActionLog.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def get_bulk_action(
    db: AsyncSession, log_id: int, organization_id: int,
) -> BulkActionLog | None:
    result = await db.execute(
        select(BulkActionLog).where(
            BulkActionLog.id == log_id,
            BulkActionLog.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def get_bulk_action_summary(
    db: AsyncSession, organization_id: int,
) -> dict:
    items = await list_bulk_actions(db, organization_id, limit=1000)
    total_records = sum(i.total_records for i in items)
    total_success = sum(i.success_count for i in items)
    total_failures = sum(i.failure_count for i in items)
    by_action: dict[str, int] = {}
    for item in items:
        by_action[item.action_type] = by_action.get(item.action_type, 0) + 1
    return {
        "total_operations": len(items),
        "total_records_processed": total_records,
        "total_success": total_success,
        "total_failures": total_failures,
        "by_action_type": by_action,
    }
