from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.user import UserCreate, UserRead
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
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> UserRead:
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    existing = await user_service.get_user_by_email(db, data.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already exists")
    created = await user_service.create_user(db, data)
    await record_action(
        db,
        event_type="user_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="user",
        entity_id=created.id,
        payload_json={"email": created.email, "role": created.role},
    )
    return created
