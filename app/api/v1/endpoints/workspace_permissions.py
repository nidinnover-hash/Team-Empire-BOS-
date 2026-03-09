"""Workspace permission endpoints — manage memberships and check access."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import workspace_permissions as perm_service

router = APIRouter(prefix="/workspace-perms", tags=["Workspace Permissions"])


class AddMemberRequest(BaseModel):
    user_id: int
    role_override: str | None = Field(None, max_length=30)


@router.get("")
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> list[dict]:
    """List all active workspaces in the organization."""
    workspaces = await perm_service.list_workspaces(db, organization_id=actor["org_id"])
    return [
        {
            "id": ws.id,
            "name": ws.name,
            "slug": ws.slug,
            "workspace_type": ws.workspace_type,
            "is_default": ws.is_default,
        }
        for ws in workspaces
    ]


@router.get("/my")
async def get_my_workspaces(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> list[dict]:
    """Get workspaces the current user is a member of."""
    return await perm_service.get_user_workspaces(
        db, user_id=int(actor["id"]), organization_id=actor["org_id"],
    )


@router.get("/{workspace_id}/members")
async def list_workspace_members(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    """List members of a workspace."""
    return await perm_service.list_members(db, workspace_id=workspace_id)


@router.post("/{workspace_id}/members", status_code=201)
async def add_workspace_member(
    workspace_id: int,
    data: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Add a user to a workspace."""
    membership = await perm_service.add_member(
        db, workspace_id=workspace_id, user_id=data.user_id,
        role_override=data.role_override,
    )
    return {
        "workspace_id": membership.workspace_id,
        "user_id": membership.user_id,
        "role_override": membership.role_override,
        "is_active": membership.is_active,
    }


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
async def remove_workspace_member(
    workspace_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    """Remove a user from a workspace."""
    removed = await perm_service.remove_member(db, workspace_id=workspace_id, user_id=user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Membership not found")


@router.get("/{workspace_id}/check-access/{user_id}")
async def check_workspace_access(
    workspace_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Check if a user has access to a workspace."""
    result = await perm_service.check_access(db, workspace_id=workspace_id, user_id=user_id)
    if result is None:
        return {"has_access": False, "workspace_id": workspace_id}
    return result
