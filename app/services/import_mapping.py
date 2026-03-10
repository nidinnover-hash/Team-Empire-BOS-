"""Contact import mapping service."""
from __future__ import annotations

import json

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_mapping import ImportMapping, ImportHistory


async def create_mapping(
    db: AsyncSession, *, organization_id: int, name: str,
    entity_type: str = "contact", column_map: dict | None = None,
    transformers: list[dict] | None = None,
) -> ImportMapping:
    row = ImportMapping(
        organization_id=organization_id, name=name,
        entity_type=entity_type,
        column_map_json=json.dumps(column_map or {}),
        transformers_json=json.dumps(transformers or []),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_mappings(
    db: AsyncSession, organization_id: int, *,
    entity_type: str | None = None,
) -> list[ImportMapping]:
    q = select(ImportMapping).where(ImportMapping.organization_id == organization_id)
    if entity_type:
        q = q.where(ImportMapping.entity_type == entity_type)
    q = q.order_by(ImportMapping.name)
    return list((await db.execute(q)).scalars().all())


async def get_mapping(db: AsyncSession, mapping_id: int, organization_id: int) -> ImportMapping | None:
    q = select(ImportMapping).where(ImportMapping.id == mapping_id, ImportMapping.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_mapping(db: AsyncSession, mapping_id: int, organization_id: int, **kwargs) -> ImportMapping | None:
    row = await get_mapping(db, mapping_id, organization_id)
    if not row:
        return None
    if "column_map" in kwargs:
        kwargs["column_map_json"] = json.dumps(kwargs.pop("column_map") or {})
    if "transformers" in kwargs:
        kwargs["transformers_json"] = json.dumps(kwargs.pop("transformers") or [])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_mapping(db: AsyncSession, mapping_id: int, organization_id: int) -> bool:
    row = await get_mapping(db, mapping_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def record_import(
    db: AsyncSession, *, organization_id: int,
    file_name: str, entity_type: str = "contact",
    mapping_id: int | None = None,
    total_rows: int = 0, success_rows: int = 0,
    error_rows: int = 0, status: str = "completed",
    errors: list[dict] | None = None,
    started_by_user_id: int | None = None,
) -> ImportHistory:
    row = ImportHistory(
        organization_id=organization_id, mapping_id=mapping_id,
        file_name=file_name, entity_type=entity_type,
        total_rows=total_rows, success_rows=success_rows,
        error_rows=error_rows, status=status,
        errors_json=json.dumps(errors or []),
        started_by_user_id=started_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_imports(
    db: AsyncSession, organization_id: int, *,
    entity_type: str | None = None, limit: int = 50,
) -> list[ImportHistory]:
    q = select(ImportHistory).where(ImportHistory.organization_id == organization_id)
    if entity_type:
        q = q.where(ImportHistory.entity_type == entity_type)
    q = q.order_by(ImportHistory.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_import_stats(db: AsyncSession, organization_id: int) -> dict:
    total = (await db.execute(
        select(func.count(ImportHistory.id)).where(ImportHistory.organization_id == organization_id)
    )).scalar() or 0
    success = (await db.execute(
        select(func.coalesce(func.sum(ImportHistory.success_rows), 0)).where(ImportHistory.organization_id == organization_id)
    )).scalar() or 0
    errors = (await db.execute(
        select(func.coalesce(func.sum(ImportHistory.error_rows), 0)).where(ImportHistory.organization_id == organization_id)
    )).scalar() or 0
    return {"total_imports": total, "total_success_rows": int(success), "total_error_rows": int(errors)}
