from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from app.services import contact as contact_service

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("", response_model=ContactRead, status_code=201)
async def create_contact(
    data: ContactCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ContactRead:
    """Add a person to your network."""
    contact = await contact_service.create_contact(db, data, organization_id=actor["org_id"])
    await record_action(
        db,
        event_type="contact_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="contact",
        entity_id=contact.id,
        payload_json={"name": data.name},
    )
    return contact


@router.get("", response_model=list[ContactRead])
async def list_contacts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[ContactRead]:
    """List all contacts, alphabetically by name."""
    return await contact_service.list_contacts(db, organization_id=actor["org_id"], limit=limit, offset=offset)


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ContactRead:
    contact = await contact_service.get_contact(db, contact_id, organization_id=actor["org_id"])
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: int,
    data: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ContactRead:
    contact = await contact_service.update_contact(db, contact_id, data, organization_id=actor["org_id"])
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await record_action(
        db, event_type="contact_updated", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="contact", entity_id=contact_id,
    )
    return contact


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await contact_service.delete_contact(db, contact_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found")
    await record_action(
        db, event_type="contact_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="contact", entity_id=contact_id,
    )
