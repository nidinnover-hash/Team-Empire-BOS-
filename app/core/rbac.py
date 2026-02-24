from typing import Literal

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_user

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
]


def require_roles(*allowed_roles: Role):
    allowed = set(allowed_roles)

    def dependency(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role", "STAFF")
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' does not have access",
            )
        return user

    return dependency
