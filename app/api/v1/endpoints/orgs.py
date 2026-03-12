from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.idempotency import (
    IdempotencyConflictError,
    build_fingerprint,
    get_cached_response,
    store_response,
)
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.org_membership import OrganizationMembershipCreate, OrganizationMembershipRead
from app.schemas.organization import (
    FeatureFlagValue,
    OrganizationCreate,
    OrganizationFeatureFlagsRead,
    OrganizationFeatureFlagsUpdate,
    OrganizationRead,
    OrganizationUpdate,
)
from app.services import org_membership as membership_service
from app.services import organization as organization_service

router = APIRouter(prefix="/orgs", tags=["Organizations"])


@router.get("", response_model=list[OrganizationRead])
async def list_orgs(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[OrganizationRead]:
    org = await organization_service.get_organization_by_id(db, actor["org_id"])
    return [org] if org else []  # type: ignore[list-item]


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_org(
    data: OrganizationCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> OrganizationRead:
    scope = f"org_create:{int(actor['org_id'])}"
    fingerprint = build_fingerprint(data.model_dump())
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return OrganizationRead.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
    existing = await organization_service.get_organization_by_slug(db, data.slug)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Slug already exists")
    org = await organization_service.create_organization(
        db,
        name=data.name,
        slug=data.slug,
        parent_organization_id=data.parent_organization_id,
        country_code=data.country_code,
        branch_label=data.branch_label,
        industry_type=data.industry_type,
    )
    await record_action(
        db,
        event_type="security_organization_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="organization",
        entity_id=org.id,
        payload_json={"slug": org.slug},
    )
    if idempotency_key:
        store_response(
            scope,
            idempotency_key,
            jsonable_encoder(OrganizationRead.model_validate(org)),
            fingerprint=fingerprint,
        )
    return org


@router.patch("/{org_id}", response_model=OrganizationRead)
async def update_org(
    org_id: int,
    data: OrganizationUpdate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> OrganizationRead:
    if org_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot modify another organization")
    payload = data.model_dump(exclude_unset=True)
    scope = f"org_update:{int(actor['org_id'])}:{org_id}"
    fingerprint = build_fingerprint(payload)
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return OrganizationRead.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
    org = await organization_service.update_organization(
        db,
        organization_id=org_id,
        name=payload.get("name"),
        slug=payload.get("slug"),
        parent_organization_id=payload.get("parent_organization_id"),
        country_code=payload.get("country_code"),
        branch_label=payload.get("branch_label"),
        industry_type=payload.get("industry_type"),
        expected_config_version=payload.get("expected_config_version"),
    )
    if org is None:
        raise HTTPException(status_code=409, detail="Organization update conflict or not found")
    await record_action(
        db,
        event_type="security_organization_updated",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="organization",
        entity_id=org.id,
        payload_json={"name": org.name, "slug": org.slug, "config_version": org.config_version},
    )
    if idempotency_key:
        store_response(
            scope,
            idempotency_key,
            jsonable_encoder(OrganizationRead.model_validate(org)),
            fingerprint=fingerprint,
        )
    return org


@router.get("/{org_id}/feature-flags", response_model=OrganizationFeatureFlagsRead)
async def get_org_feature_flags(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> OrganizationFeatureFlagsRead:
    if org_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot view another organization's settings")
    version, flags = await organization_service.get_feature_flags(db, org_id)
    normalized = {key: FeatureFlagValue.model_validate(value) for key, value in flags.items()}
    return OrganizationFeatureFlagsRead(config_version=version, flags=normalized)


@router.patch("/{org_id}/feature-flags", response_model=OrganizationFeatureFlagsRead)
async def update_org_feature_flags(
    org_id: int,
    data: OrganizationFeatureFlagsUpdate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> OrganizationFeatureFlagsRead:
    if org_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot modify another organization's settings")
    body = data.model_dump(exclude_unset=True)
    scope = f"org_feature_flags:{int(actor['org_id'])}:{org_id}"
    fingerprint = build_fingerprint(body)
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return OrganizationFeatureFlagsRead.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
    updated = await organization_service.update_feature_flags(
        db,
        organization_id=org_id,
        flags=body.get("flags", {}),
        expected_config_version=body.get("expected_config_version"),
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="Feature flag update conflict or organization not found")
    version, flags = updated
    normalized = {key: FeatureFlagValue.model_validate(value) for key, value in flags.items()}
    await record_action(
        db,
        event_type="security_feature_flags_updated",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="organization",
        entity_id=org_id,
        payload_json={"config_version": version, "flags": list(flags.keys())},
    )
    response = OrganizationFeatureFlagsRead(config_version=version, flags=normalized)
    if idempotency_key:
        store_response(
            scope,
            idempotency_key,
            jsonable_encoder(response),
            fingerprint=fingerprint,
        )
    return response


@router.get("/{org_id}/members", response_model=list[OrganizationMembershipRead])
async def list_org_members(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[OrganizationMembershipRead]:
    if org_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot view another organization's members")
    return await membership_service.list_memberships(db, organization_id=org_id)


@router.post("/{org_id}/members", response_model=OrganizationMembershipRead, status_code=201)
async def upsert_org_member(
    org_id: int,
    data: OrganizationMembershipCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> OrganizationMembershipRead:
    if org_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cannot modify another organization's members")
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
