from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactUpdate


async def create_contact(
    db: AsyncSession, data: ContactCreate, organization_id: int
) -> Contact:
    contact = Contact(**data.model_dump(), organization_id=organization_id)
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


async def list_contacts(
    db: AsyncSession, organization_id: int, limit: int = 100, offset: int = 0
) -> list[Contact]:
    result = await db.execute(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .order_by(Contact.name)
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_contact(
    db: AsyncSession, contact_id: int, organization_id: int,
) -> Contact | None:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def update_contact(
    db: AsyncSession, contact_id: int, data: ContactUpdate, organization_id: int,
) -> Contact | None:
    contact = await get_contact(db, contact_id, organization_id)
    if contact is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    return contact


async def delete_contact(
    db: AsyncSession, contact_id: int, organization_id: int,
) -> bool:
    contact = await get_contact(db, contact_id, organization_id)
    if contact is None:
        return False
    await db.delete(contact)
    await db.commit()
    return True
