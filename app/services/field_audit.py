"""Field-level audit log service — record and query field changes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.field_audit import FieldAuditEntry


async def record_change(
    db: AsyncSession, organization_id: int,
    entity_type: str, entity_id: int, field_name: str,
    old_value: str | None, new_value: str | None,
    changed_by: int | None = None, change_source: str = "api",
) -> FieldAuditEntry:
    entry = FieldAuditEntry(
        organization_id=organization_id, entity_type=entity_type,
        entity_id=entity_id, field_name=field_name,
        old_value=old_value, new_value=new_value,
        changed_by_user_id=changed_by, change_source=change_source,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def record_changes_batch(
    db: AsyncSession, organization_id: int,
    entity_type: str, entity_id: int,
    changes: list[dict], changed_by: int | None = None,
    change_source: str = "api",
) -> list[FieldAuditEntry]:
    entries = []
    for change in changes:
        entry = FieldAuditEntry(
            organization_id=organization_id, entity_type=entity_type,
            entity_id=entity_id, field_name=change["field"],
            old_value=change.get("old"), new_value=change.get("new"),
            changed_by_user_id=changed_by, change_source=change_source,
        )
        db.add(entry)
        entries.append(entry)
    await db.commit()
    for e in entries:
        await db.refresh(e)
    return entries


async def get_entity_history(
    db: AsyncSession, organization_id: int,
    entity_type: str, entity_id: int, limit: int = 100,
) -> list[FieldAuditEntry]:
    result = await db.execute(
        select(FieldAuditEntry).where(
            FieldAuditEntry.organization_id == organization_id,
            FieldAuditEntry.entity_type == entity_type,
            FieldAuditEntry.entity_id == entity_id,
        ).order_by(FieldAuditEntry.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_field_history(
    db: AsyncSession, organization_id: int,
    entity_type: str, entity_id: int, field_name: str, limit: int = 50,
) -> list[FieldAuditEntry]:
    result = await db.execute(
        select(FieldAuditEntry).where(
            FieldAuditEntry.organization_id == organization_id,
            FieldAuditEntry.entity_type == entity_type,
            FieldAuditEntry.entity_id == entity_id,
            FieldAuditEntry.field_name == field_name,
        ).order_by(FieldAuditEntry.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_recent_changes(
    db: AsyncSession, organization_id: int,
    entity_type: str | None = None, limit: int = 50,
) -> list[FieldAuditEntry]:
    q = select(FieldAuditEntry).where(FieldAuditEntry.organization_id == organization_id)
    if entity_type:
        q = q.where(FieldAuditEntry.entity_type == entity_type)
    result = await db.execute(q.order_by(FieldAuditEntry.created_at.desc()).limit(limit))
    return list(result.scalars().all())
