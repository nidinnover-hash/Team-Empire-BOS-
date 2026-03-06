from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_api_user, get_db
from app.core.visibility import (
    CEO_EXECUTIVE_ROLE_ORDER,
    CROSS_COMPANY_ROLE_ORDER,
    SENSITIVE_FINANCIAL_ROLE_ORDER,
)
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


def require_roles(*allowed_roles: Role) -> Callable[..., Awaitable[dict[str, object]]]:
    allowed = set(allowed_roles)

    async def dependency(user: dict[str, object] = Depends(get_current_api_user)) -> dict[str, object]:
        role = user.get("role", "STAFF")
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' does not have access",
            )
        return user

    return dependency


def require_sensitive_financial_roles() -> Callable[..., Awaitable[dict[str, object]]]:
    """Reusable RBAC dependency for finance-like sensitive endpoints."""
    return require_roles(*SENSITIVE_FINANCIAL_ROLE_ORDER)


def require_cross_company_roles() -> Callable[..., Awaitable[dict[str, object]]]:
    """Cross-company / multi-org rollup data — CEO only."""
    return require_roles(*CROSS_COMPANY_ROLE_ORDER)


def require_ceo_executive_roles() -> Callable[..., Awaitable[dict[str, object]]]:
    """CEO executive endpoints (board-packet, status, playbook) — CEO + ADMIN."""
    return require_roles(*CEO_EXECUTIVE_ROLE_ORDER)


async def require_super_admin(
    user: dict[str, object] = Depends(get_current_api_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    raw_user_id = user.get("id")
    if isinstance(raw_user_id, bool):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    if not isinstance(raw_user_id, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    result = await db.execute(select(User).where(User.id == raw_user_id))
    db_user = result.scalar_one_or_none()
    if db_user is None or not bool(getattr(db_user, "is_super_admin", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-admin access required",
        )
    return user
