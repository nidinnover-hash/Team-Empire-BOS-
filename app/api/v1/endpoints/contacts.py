from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.contact import ContactCreate, ContactRead
from app.services import contact as contact_service

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("", response_model=ContactRead, status_code=201)
async def create_contact(
    data: ContactCreate,
    db: AsyncSession = Depends(get_db),
) -> ContactRead:
    """Add a person to your network."""
    return await contact_service.create_contact(db, data)


@router.get("", response_model=list[ContactRead])
async def list_contacts(
    db: AsyncSession = Depends(get_db),
) -> list[ContactRead]:
    """List all contacts, alphabetically by name."""
    return await contact_service.list_contacts(db)
