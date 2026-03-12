"""Contact relationship mapping service."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_relationship import ContactRelationship


async def create_relationship(
    db: AsyncSession, *, organization_id: int,
    contact_a_id: int, contact_b_id: int,
    relationship_type: str, strength: int = 50, notes: str | None = None,
) -> ContactRelationship:
    row = ContactRelationship(
        organization_id=organization_id,
        contact_a_id=contact_a_id, contact_b_id=contact_b_id,
        relationship_type=relationship_type, strength=strength, notes=notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_relationships(
    db: AsyncSession, organization_id: int, *, contact_id: int | None = None,
) -> list[ContactRelationship]:
    q = select(ContactRelationship).where(ContactRelationship.organization_id == organization_id)
    if contact_id is not None:
        q = q.where(or_(
            ContactRelationship.contact_a_id == contact_id,
            ContactRelationship.contact_b_id == contact_id,
        ))
    q = q.order_by(ContactRelationship.strength.desc())
    return list((await db.execute(q)).scalars().all())


async def get_relationship(db: AsyncSession, rel_id: int, organization_id: int) -> ContactRelationship | None:
    q = select(ContactRelationship).where(
        ContactRelationship.id == rel_id,
        ContactRelationship.organization_id == organization_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def update_relationship(db: AsyncSession, rel_id: int, organization_id: int, **kwargs) -> ContactRelationship | None:
    row = await get_relationship(db, rel_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_relationship(db: AsyncSession, rel_id: int, organization_id: int) -> bool:
    row = await get_relationship(db, rel_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
