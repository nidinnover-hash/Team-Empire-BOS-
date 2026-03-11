"""Audit trail viewer service."""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_entry import AuditEntry


async def record_audit(
    db: AsyncSession, *, organization_id: int, entity_type: str,
    entity_id: int, action: str, user_id: int | None = None,
    changes: dict | None = None, snapshot: dict | None = None,
    ip_address: str | None = None,
) -> AuditEntry:
    row = AuditEntry(
        organization_id=organization_id, entity_type=entity_type,
        entity_id=entity_id, action=action, user_id=user_id,
        changes_json=json.dumps(changes or {}),
        snapshot_json=json.dumps(snapshot or {}),
        ip_address=ip_address,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_entries(
    db: AsyncSession, organization_id: int, *,
    entity_type: str | None = None, entity_id: int | None = None,
    action: str | None = None, user_id: int | None = None,
    limit: int = 100,
) -> list[AuditEntry]:
    q = select(AuditEntry).where(AuditEntry.organization_id == organization_id)
    if entity_type:
        q = q.where(AuditEntry.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(AuditEntry.entity_id == entity_id)
    if action:
        q = q.where(AuditEntry.action == action)
    if user_id is not None:
        q = q.where(AuditEntry.user_id == user_id)
    q = q.order_by(AuditEntry.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_entity_history(db: AsyncSession, organization_id: int, entity_type: str, entity_id: int) -> list[AuditEntry]:
    q = (
        select(AuditEntry)
        .where(AuditEntry.organization_id == organization_id, AuditEntry.entity_type == entity_type, AuditEntry.entity_id == entity_id)
        .order_by(AuditEntry.created_at.desc())
    )
    return list((await db.execute(q)).scalars().all())


async def get_stats(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(AuditEntry.action, func.count(AuditEntry.id))
        .where(AuditEntry.organization_id == organization_id)
        .group_by(AuditEntry.action)
    )).all()
    return {action: count for action, count in rows}
