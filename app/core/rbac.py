from typing import Literal

from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_api_user

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
