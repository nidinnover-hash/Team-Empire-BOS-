from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.org_membership import OrganizationMembershipCreate, OrganizationMembershipRead
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.services import org_membership as membership_service
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


@router.get("/{org_id}/members", response_model=list[OrganizationMembershipRead])
async def list_org_members(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[OrganizationMembershipRead]:
    return await membership_service.list_memberships(db, organization_id=org_id)


@router.post("/{org_id}/members", response_model=OrganizationMembershipRead, status_code=201)
async def upsert_org_member(
    org_id: int,
    data: OrganizationMembershipCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> OrganizationMembershipRead:
    membership = await membership_service.upsert_membership(
        db,
        organization_id=org_id,
        user_id=data.user_id,
        role=data.role,
    )
    await record_action(
        db,
        event_type="organization_member_upserted",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="organization_membership",
        entity_id=membership.id,
        payload_json={"target_org_id": org_id, "user_id": data.user_id, "role": data.role},
    )
    return membership
