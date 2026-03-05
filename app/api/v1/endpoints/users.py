from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
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
from app.schemas.ops import EmployeeRead
from app.schemas.user import (
    LinkEmployeeRequest,
    RoleChangeRequest,
    TeamMemberCreate,
    TeamMemberRead,
    UserCreate,
    UserRead,
    UserToggleActive,
)
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserRead])
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[UserRead]:
    return await user_service.list_users(db, organization_id=_user["org_id"], limit=limit, offset=offset)


@router.post(
    "",
    response_model=UserRead,
    status_code=201,
    deprecated=True,
    summary="Create user (deprecated — use POST /users/team-member instead)",
)
async def create_user(
    data: UserCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> UserRead:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/v1/users/team-member>; rel="successor-version"'
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


@router.post("/team-member", response_model=TeamMemberRead, status_code=201)
async def create_team_member(
    data: TeamMemberCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TeamMemberRead:
    scope = f"team_member_create:{int(actor['org_id'])}"
    fingerprint = build_fingerprint(data.model_dump())
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return TeamMemberRead.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    existing = await user_service.get_user_by_email(db, data.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already exists")
    user, employee = await user_service.create_team_member(db, data)
    await record_action(
        db,
        event_type="security_user_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="user",
        entity_id=user.id,
        payload_json={"email": user.email, "role": user.role},
    )
    await record_action(
        db,
        event_type="employee_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="employee",
        entity_id=employee.id,
        payload_json={"email": employee.email, "user_id": user.id},
    )
    result = TeamMemberRead(
        user=UserRead.model_validate(user),
        employee=EmployeeRead.model_validate(employee),
    )
    if idempotency_key:
        store_response(scope, idempotency_key, result.model_dump(), fingerprint=fingerprint)
    return result


@router.post("/{user_id}/link-employee", response_model=TeamMemberRead)
async def link_user_to_employee(
    user_id: int,
    data: LinkEmployeeRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TeamMemberRead:
    try:
        result = await user_service.link_user_to_employee(
            db, user_id=user_id, employee_id=data.employee_id, organization_id=actor["org_id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="User or employee not found")
    user, employee = result
    await record_action(
        db,
        event_type="employee_linked_to_user",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="employee",
        entity_id=employee.id,
        payload_json={"user_id": user.id, "employee_id": employee.id},
    )
    return TeamMemberRead(
        user=UserRead.model_validate(user),
        employee=EmployeeRead.model_validate(employee),
    )


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
