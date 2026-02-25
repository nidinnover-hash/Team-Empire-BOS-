from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.schemas.contact import ContactCreate


async def create_contact(
    db: AsyncSession, data: ContactCreate, organization_id: int = 1
) -> Contact:
    contact = Contact(**data.model_dump(), organization_id=organization_id)
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


async def list_contacts(
    db: AsyncSession, limit: int = 100, organization_id: int = 1
) -> list[Contact]:
    result = await db.execute(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .order_by(Contact.name)
        .limit(limit)
    )
    return list(result.scalars().all())
