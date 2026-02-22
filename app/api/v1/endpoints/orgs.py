from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.services import organization as organization_service

router = APIRouter(prefix="/orgs", tags=["Organizations"])


@router.get("", response_model=list[OrganizationRead])
async def list_orgs(
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[OrganizationRead]:
    return await organization_service.list_organizations(db)


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_org(
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> OrganizationRead:
    existing = await organization_service.get_organization_by_slug(db, data.slug)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Slug already exists")
    org = await organization_service.create_organization(db, name=data.name, slug=data.slug)
    await record_action(
        db,
        event_type="organization_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="organization",
        entity_id=org.id,
        payload_json={"slug": org.slug},
    )
    return org


@router.patch("/{org_id}", response_model=OrganizationRead)
async def update_org(
    org_id: int,
    data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> OrganizationRead:
    org = await organization_service.update_organization(
        db,
        organization_id=org_id,
        name=data.name,
        slug=data.slug,
    )
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await record_action(
        db,
        event_type="organization_updated",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="organization",
        entity_id=org.id,
        payload_json={"name": org.name, "slug": org.slug},
    )
    return org
