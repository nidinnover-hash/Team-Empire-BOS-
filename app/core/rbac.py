from typing import Literal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_api_user, get_db
from app.models.user import User

Role = Literal[
    "CEO",
    "ADMIN",
    "MANAGER",
    "STAFF",
    "OWNER",
    "TECH_LEAD",
    "OPS_MANAGER",
    "DEVELOPER",
    "VIEWER",
    "EMPLOYEE",
]


def require_roles(*allowed_roles: Role):
    allowed = set(allowed_roles)

    async def dependency(user: dict = Depends(get_current_api_user)) -> dict:
        role = user.get("role", "STAFF")
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' does not have access",
            )
        return user

    return dependency


async def require_super_admin(
    user: dict = Depends(get_current_api_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(User).where(User.id == int(user["id"])))
    db_user = result.scalar_one_or_none()
    if db_user is None or not bool(getattr(db_user, "is_super_admin", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-admin access required",
        )
    return user
