from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.contact import ContactCreate, ContactRead
from app.services import contact as contact_service

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("", response_model=ContactRead, status_code=201)
async def create_contact(
    data: ContactCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ContactRead:
    """Add a person to your network."""
    return await contact_service.create_contact(db, data, organization_id=actor["org_id"])


@router.get("", response_model=list[ContactRead])
async def list_contacts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[ContactRead]:
    """List all contacts, alphabetically by name."""
    return await contact_service.list_contacts(db, organization_id=actor["org_id"], limit=limit, offset=offset)
