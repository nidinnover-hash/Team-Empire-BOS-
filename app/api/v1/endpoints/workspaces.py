"""Workspace CRUD + membership endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberRead,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services import workspace as workspace_service

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(
    active_only: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[WorkspaceRead]:
    return await workspace_service.list_workspaces(
        db, org_id=int(user["org_id"]), active_only=active_only, skip=skip, limit=limit,
    )


@router.post("", response_model=WorkspaceRead, status_code=201)
async def create_workspace(
    data: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkspaceRead:
    ws = await workspace_service.create_workspace(
        db, org_id=int(user["org_id"]), data=data,
    )
    await record_action(
        db,
        event_type="workspace.create",
        actor_user_id=int(user["id"]),
        organization_id=int(user["org_id"]),
    )
    await db.commit()
    return ws


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> WorkspaceRead:
    ws = await workspace_service.get_workspace(
        db, org_id=int(user["org_id"]), workspace_id=workspace_id,
    )
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: int,
    data: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkspaceRead:
    ws = await workspace_service.update_workspace(
        db, org_id=int(user["org_id"]), workspace_id=workspace_id, data=data,
    )
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await record_action(
        db,
        event_type="workspace.update",
        actor_user_id=int(user["id"]),
        organization_id=int(user["org_id"]),
    )
    await db.commit()
    return ws


# ── Members ──────────────────────────────────────────────────────────────────

@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberRead])
async def list_workspace_members(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[WorkspaceMemberRead]:
    ws = await workspace_service.get_workspace(
        db, org_id=int(user["org_id"]), workspace_id=workspace_id,
    )
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return await workspace_service.list_members(db, workspace_id=workspace_id)


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberRead, status_code=201)
async def add_workspace_member(
    workspace_id: int,
    data: WorkspaceMemberAdd,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkspaceMemberRead:
    ws = await workspace_service.get_workspace(
        db, org_id=int(user["org_id"]), workspace_id=workspace_id,
    )
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    m = await workspace_service.add_member(
        db, workspace_id=workspace_id, user_id=data.user_id, role_override=data.role_override,
    )
    await record_action(
        db,
        event_type="workspace.member_add",
        actor_user_id=int(user["id"]),
        organization_id=int(user["org_id"]),
    )
    await db.commit()
    return m


@router.delete("/{workspace_id}/members/{member_user_id}", status_code=204)
async def remove_workspace_member(
    workspace_id: int,
    member_user_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    ws = await workspace_service.get_workspace(
        db, org_id=int(user["org_id"]), workspace_id=workspace_id,
    )
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    removed = await workspace_service.remove_member(
        db, workspace_id=workspace_id, user_id=member_user_id,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found in workspace")
    await record_action(
        db,
        event_type="workspace.member_remove",
        actor_user_id=int(user["id"]),
        organization_id=int(user["org_id"]),
    )
    await db.commit()
