"""Generic soft-delete restore service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.deal import Deal
from app.models.goal import Goal
from app.models.project import Project
from app.models.task import Task

_MODEL_MAP: dict[str, type] = {
    "contact": Contact,
    "task": Task,
    "deal": Deal,
    "goal": Goal,
    "project": Project,
}


async def restore(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    organization_id: int,
) -> object | None:
    """Restore a soft-deleted record. Returns the restored record or None."""
    model = _MODEL_MAP.get(entity_type)
    if model is None:
        return None
    result = await db.execute(
        select(model).where(
            model.id == entity_id,
            model.organization_id == organization_id,
            model.is_deleted.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.is_deleted = False
    row.deleted_at = None
    await db.commit()
    await db.refresh(row)
    return row


async def purge(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    organization_id: int,
) -> bool:
    """Hard-delete a soft-deleted record (GDPR compliance). Returns True if purged."""
    model = _MODEL_MAP.get(entity_type)
    if model is None:
        return False
    result = await db.execute(
        select(model).where(
            model.id == entity_id,
            model.organization_id == organization_id,
            model.is_deleted.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True
