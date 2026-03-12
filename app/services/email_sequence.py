"""Email sequence automation service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_sequence import EmailSequence, EmailSequenceStep


async def create_sequence(
    db: AsyncSession, *, organization_id: int, name: str,
    trigger_event: str, description: str | None = None,
    exit_condition: str | None = None, created_by_user_id: int | None = None,
) -> EmailSequence:
    seq = EmailSequence(
        organization_id=organization_id, name=name,
        trigger_event=trigger_event, description=description,
        exit_condition=exit_condition, created_by_user_id=created_by_user_id,
    )
    db.add(seq)
    await db.commit()
    await db.refresh(seq)
    return seq


async def list_sequences(
    db: AsyncSession, organization_id: int, *, is_active: bool | None = None,
) -> list[EmailSequence]:
    q = select(EmailSequence).where(EmailSequence.organization_id == organization_id)
    if is_active is not None:
        q = q.where(EmailSequence.is_active == is_active)
    q = q.order_by(EmailSequence.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_sequence(db: AsyncSession, sequence_id: int, organization_id: int) -> EmailSequence | None:
    q = select(EmailSequence).where(
        EmailSequence.id == sequence_id,
        EmailSequence.organization_id == organization_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def update_sequence(db: AsyncSession, sequence_id: int, organization_id: int, **kwargs) -> EmailSequence | None:
    seq = await get_sequence(db, sequence_id, organization_id)
    if not seq:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(seq, k, v)
    await db.commit()
    await db.refresh(seq)
    return seq


async def delete_sequence(db: AsyncSession, sequence_id: int, organization_id: int) -> bool:
    seq = await get_sequence(db, sequence_id, organization_id)
    if not seq:
        return False
    await db.delete(seq)
    await db.commit()
    return True


async def add_step(
    db: AsyncSession, *, sequence_id: int, step_order: int = 1,
    delay_hours: int = 24, subject: str, body: str, template_id: int | None = None,
) -> EmailSequenceStep:
    step = EmailSequenceStep(
        sequence_id=sequence_id, step_order=step_order,
        delay_hours=delay_hours, subject=subject, body=body,
        template_id=template_id,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def list_steps(db: AsyncSession, sequence_id: int) -> list[EmailSequenceStep]:
    q = (
        select(EmailSequenceStep)
        .where(EmailSequenceStep.sequence_id == sequence_id)
        .order_by(EmailSequenceStep.step_order)
    )
    return list((await db.execute(q)).scalars().all())


async def delete_step(db: AsyncSession, step_id: int) -> bool:
    q = select(EmailSequenceStep).where(EmailSequenceStep.id == step_id)
    step = (await db.execute(q)).scalar_one_or_none()
    if not step:
        return False
    await db.delete(step)
    await db.commit()
    return True


async def get_stats(db: AsyncSession, organization_id: int) -> dict:
    total = (await db.execute(
        select(func.count(EmailSequence.id)).where(EmailSequence.organization_id == organization_id)
    )).scalar() or 0
    active = (await db.execute(
        select(func.count(EmailSequence.id)).where(
            EmailSequence.organization_id == organization_id,
            EmailSequence.is_active is True,
        )
    )).scalar() or 0
    enrolled = (await db.execute(
        select(func.coalesce(func.sum(EmailSequence.total_enrolled), 0)).where(
            EmailSequence.organization_id == organization_id,
        )
    )).scalar() or 0
    return {"total_sequences": total, "active_sequences": active, "total_enrolled": enrolled}
