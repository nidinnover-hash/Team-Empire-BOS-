"""Deal collaboration service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal_collaborator import DealCollaborator

ROLES = ["owner", "support", "reviewer", "observer"]


async def add_collaborator(
    db: AsyncSession, *, organization_id: int, deal_id: int,
    user_id: int, role: str = "support", notes: str | None = None,
    added_by_user_id: int | None = None,
) -> DealCollaborator:
    row = DealCollaborator(
        organization_id=organization_id, deal_id=deal_id,
        user_id=user_id, role=role, notes=notes,
        added_by_user_id=added_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_collaborators(
    db: AsyncSession, organization_id: int, deal_id: int,
) -> list[DealCollaborator]:
    q = (
        select(DealCollaborator)
        .where(
            DealCollaborator.organization_id == organization_id,
            DealCollaborator.deal_id == deal_id,
        )
        .order_by(DealCollaborator.created_at)
    )
    return list((await db.execute(q)).scalars().all())


async def update_collaborator(db: AsyncSession, collab_id: int, organization_id: int, **kwargs) -> DealCollaborator | None:
    q = select(DealCollaborator).where(DealCollaborator.id == collab_id, DealCollaborator.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def remove_collaborator(db: AsyncSession, collab_id: int, organization_id: int) -> bool:
    q = select(DealCollaborator).where(DealCollaborator.id == collab_id, DealCollaborator.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def get_user_deals(db: AsyncSession, organization_id: int, user_id: int) -> list[DealCollaborator]:
    q = (
        select(DealCollaborator)
        .where(DealCollaborator.organization_id == organization_id, DealCollaborator.user_id == user_id)
        .order_by(DealCollaborator.created_at.desc())
    )
    return list((await db.execute(q)).scalars().all())
