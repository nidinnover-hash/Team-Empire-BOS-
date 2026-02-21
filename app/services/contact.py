from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.schemas.contact import ContactCreate


async def create_contact(db: AsyncSession, data: ContactCreate) -> Contact:
    contact = Contact(**data.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


async def list_contacts(db: AsyncSession, limit: int = 100) -> list[Contact]:
    result = await db.execute(
        select(Contact).order_by(Contact.name).limit(limit)
    )
    return list(result.scalars().all())
