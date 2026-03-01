from fastapi import APIRouter, Depends, Header, HTTPException, Query
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
from app.schemas.user import RoleChangeRequest, UserCreate, UserRead, UserToggleActive
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserRead])
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[UserRead]:
    return await user_service.list_users(db, organization_id=_user["org_id"], limit=limit, offset=offset)


@router.post("", response_model=UserRead, status_code=201)
async def create_user(
    data: UserCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> UserRead:
    scope = f"user_create:{int(actor['org_id'])}"
    fingerprint = build_fingerprint(data.model_dump())
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return UserRead.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    existing = await user_service.get_user_by_email(db, data.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already exists")
    created = await user_service.create_user(db, data)
    await record_action(
        db,
        event_type="security_user_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="user",
        entity_id=created.id,
        payload_json={"email": created.email, "role": created.role},
    )
    if idempotency_key:
        store_response(scope, idempotency_key, UserRead.model_validate(created).model_dump(), fingerprint=fingerprint)
    return created


@router.patch("/{user_id}/role", response_model=UserRead)
async def change_user_role(
    user_id: int,
    data: RoleChangeRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> UserRead:
    scope = f"user_role_change:{int(actor['org_id'])}:{user_id}"
    fingerprint = build_fingerprint(data.model_dump())
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return UserRead.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
    updated = await user_service.update_user_role(
        db, user_id=user_id, organization_id=int(actor["org_id"]), new_role=data.role,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found or invalid role")
    await record_action(
        db,
        event_type="security_user_role_changed",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="user",
        entity_id=user_id,
        payload_json={"new_role": data.role},
    )
    if idempotency_key:
        store_response(scope, idempotency_key, UserRead.model_validate(updated).model_dump(), fingerprint=fingerprint)
    return updated


@router.patch("/{user_id}/active", response_model=UserRead)
async def toggle_user_active(
    user_id: int,
    data: UserToggleActive,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> UserRead:
    scope = f"user_active_toggle:{int(actor['org_id'])}:{user_id}"
    fingerprint = build_fingerprint(data.model_dump())
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return UserRead.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
    updated = await user_service.toggle_user_active(
        db, user_id=user_id, organization_id=int(actor["org_id"]), is_active=data.is_active,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    await record_action(
        db,
        event_type="security_user_active_toggled",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="user",
        entity_id=user_id,
        payload_json={"is_active": data.is_active},
    )
    if idempotency_key:
        store_response(scope, idempotency_key, UserRead.model_validate(updated).model_dump(), fingerprint=fingerprint)
    return updated
