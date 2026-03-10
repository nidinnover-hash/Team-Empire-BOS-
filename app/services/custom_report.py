"""Custom report builder service."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_report import ReportDefinition


async def create_report(
    db: AsyncSession, *, organization_id: int, name: str,
    description: str | None = None, entity_type: str = "deal",
    filters: dict | None = None, grouping: list[str] | None = None,
    aggregation: list[dict] | None = None, columns: list[str] | None = None,
    is_shared: bool = False, created_by_user_id: int | None = None,
) -> ReportDefinition:
    row = ReportDefinition(
        organization_id=organization_id, name=name,
        description=description, entity_type=entity_type,
        filters_json=json.dumps(filters or {}),
        grouping_json=json.dumps(grouping or []),
        aggregation_json=json.dumps(aggregation or []),
        columns_json=json.dumps(columns or []),
        is_shared=is_shared,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_reports(
    db: AsyncSession, organization_id: int, *,
    entity_type: str | None = None, is_shared: bool | None = None,
) -> list[ReportDefinition]:
    q = select(ReportDefinition).where(ReportDefinition.organization_id == organization_id)
    if entity_type:
        q = q.where(ReportDefinition.entity_type == entity_type)
    if is_shared is not None:
        q = q.where(ReportDefinition.is_shared == is_shared)
    q = q.order_by(ReportDefinition.name)
    return list((await db.execute(q)).scalars().all())


async def get_report(db: AsyncSession, report_id: int, organization_id: int) -> ReportDefinition | None:
    q = select(ReportDefinition).where(ReportDefinition.id == report_id, ReportDefinition.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_report(db: AsyncSession, report_id: int, organization_id: int, **kwargs) -> ReportDefinition | None:
    row = await get_report(db, report_id, organization_id)
    if not row:
        return None
    for key in ("filters", "grouping", "aggregation", "columns"):
        if key in kwargs:
            kwargs[f"{key}_json"] = json.dumps(kwargs.pop(key) or ([] if key != "filters" else {}))
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_report(db: AsyncSession, report_id: int, organization_id: int) -> bool:
    row = await get_report(db, report_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def record_run(db: AsyncSession, report_id: int, organization_id: int) -> ReportDefinition | None:
    row = await get_report(db, report_id, organization_id)
    if not row:
        return None
    row.run_count += 1
    row.last_run_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row
