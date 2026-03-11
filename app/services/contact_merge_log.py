"""Contact merge log service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_merge_log import ContactMergeLog


async def record_merge(db: AsyncSession, *, organization_id: int, **kw) -> ContactMergeLog:
    row = ContactMergeLog(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_merge(db: AsyncSession, merge_id: int, org_id: int) -> ContactMergeLog | None:
    return (await db.execute(select(ContactMergeLog).where(ContactMergeLog.id == merge_id, ContactMergeLog.organization_id == org_id))).scalar_one_or_none()


async def list_merges(db: AsyncSession, org_id: int, *, contact_id: int | None = None, limit: int = 50) -> list[ContactMergeLog]:
    q = select(ContactMergeLog).where(ContactMergeLog.organization_id == org_id)
    if contact_id:
        q = q.where(
            (ContactMergeLog.primary_contact_id == contact_id) | (ContactMergeLog.merged_contact_id == contact_id)
        )
    q = q.order_by(ContactMergeLog.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_stats(db: AsyncSession, org_id: int) -> dict:
    total = (await db.execute(select(func.count(ContactMergeLog.id)).where(ContactMergeLog.organization_id == org_id))).scalar() or 0
    completed = (await db.execute(
        select(func.count(ContactMergeLog.id)).where(ContactMergeLog.organization_id == org_id, ContactMergeLog.status == "completed")
    )).scalar() or 0
    return {"total": total, "completed": completed, "reverted": total - completed}
