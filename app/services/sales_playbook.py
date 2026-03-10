"""Sales playbook service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales_playbook import Playbook, PlaybookStep


async def create_playbook(
    db: AsyncSession, *, organization_id: int, name: str,
    deal_stage: str | None = None, description: str | None = None,
    is_active: bool = True,
) -> Playbook:
    row = Playbook(
        organization_id=organization_id, name=name,
        deal_stage=deal_stage, description=description,
        is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_playbooks(
    db: AsyncSession, organization_id: int, *,
    deal_stage: str | None = None, is_active: bool | None = None,
) -> list[Playbook]:
    q = select(Playbook).where(Playbook.organization_id == organization_id)
    if deal_stage:
        q = q.where(Playbook.deal_stage == deal_stage)
    if is_active is not None:
        q = q.where(Playbook.is_active == is_active)
    q = q.order_by(Playbook.name)
    return list((await db.execute(q)).scalars().all())


async def get_playbook(db: AsyncSession, playbook_id: int, organization_id: int) -> Playbook | None:
    q = select(Playbook).where(Playbook.id == playbook_id, Playbook.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_playbook(db: AsyncSession, playbook_id: int, organization_id: int, **kwargs) -> Playbook | None:
    row = await get_playbook(db, playbook_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_playbook(db: AsyncSession, playbook_id: int, organization_id: int) -> bool:
    row = await get_playbook(db, playbook_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def add_step(
    db: AsyncSession, *, organization_id: int, playbook_id: int,
    title: str, step_order: int = 0, content: str | None = None,
    is_required: bool = False,
) -> PlaybookStep:
    step = PlaybookStep(
        organization_id=organization_id, playbook_id=playbook_id,
        step_order=step_order, title=title, content=content,
        is_required=is_required,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def list_steps(db: AsyncSession, organization_id: int, playbook_id: int) -> list[PlaybookStep]:
    q = (
        select(PlaybookStep)
        .where(PlaybookStep.organization_id == organization_id, PlaybookStep.playbook_id == playbook_id)
        .order_by(PlaybookStep.step_order)
    )
    return list((await db.execute(q)).scalars().all())


async def delete_step(db: AsyncSession, step_id: int, organization_id: int) -> bool:
    q = select(PlaybookStep).where(PlaybookStep.id == step_id, PlaybookStep.organization_id == organization_id)
    step = (await db.execute(q)).scalar_one_or_none()
    if not step:
        return False
    await db.delete(step)
    await db.commit()
    return True
