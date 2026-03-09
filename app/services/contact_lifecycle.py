"""Contact lifecycle service — stage progression tracking."""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_lifecycle import ContactLifecycleEvent, LIFECYCLE_STAGES


async def transition_stage(
    db: AsyncSession, organization_id: int, contact_id: int,
    to_stage: str, from_stage: str | None = None,
    changed_by: int | None = None, reason: str | None = None,
) -> ContactLifecycleEvent:
    event = ContactLifecycleEvent(
        organization_id=organization_id, contact_id=contact_id,
        from_stage=from_stage, to_stage=to_stage,
        changed_by_user_id=changed_by, reason=reason,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_contact_history(
    db: AsyncSession, organization_id: int, contact_id: int,
) -> list[ContactLifecycleEvent]:
    result = await db.execute(
        select(ContactLifecycleEvent).where(
            ContactLifecycleEvent.organization_id == organization_id,
            ContactLifecycleEvent.contact_id == contact_id,
        ).order_by(ContactLifecycleEvent.created_at)
    )
    return list(result.scalars().all())


async def get_current_stage(
    db: AsyncSession, organization_id: int, contact_id: int,
) -> str | None:
    result = await db.execute(
        select(ContactLifecycleEvent).where(
            ContactLifecycleEvent.organization_id == organization_id,
            ContactLifecycleEvent.contact_id == contact_id,
        ).order_by(ContactLifecycleEvent.created_at.desc()).limit(1)
    )
    event = result.scalar_one_or_none()
    return event.to_stage if event else None


async def get_stage_counts(
    db: AsyncSession, organization_id: int,
) -> dict:
    """Count contacts at each lifecycle stage (based on latest event per contact)."""
    # Get the latest event per contact using a subquery
    latest_sq = (
        select(
            ContactLifecycleEvent.contact_id,
            func.max(ContactLifecycleEvent.id).label("max_id"),
        )
        .where(ContactLifecycleEvent.organization_id == organization_id)
        .group_by(ContactLifecycleEvent.contact_id)
        .subquery()
    )
    result = await db.execute(
        select(ContactLifecycleEvent.to_stage, func.count())
        .join(latest_sq, ContactLifecycleEvent.id == latest_sq.c.max_id)
        .group_by(ContactLifecycleEvent.to_stage)
    )
    counts = {stage: 0 for stage in LIFECYCLE_STAGES}
    for stage, count in result.all():
        counts[stage] = count
    return {"stages": LIFECYCLE_STAGES, "counts": counts}
