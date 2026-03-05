"""Workspace CRUD service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate


async def list_workspaces(
    db: AsyncSession,
    org_id: int,
    *,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
) -> list[Workspace]:
    q = select(Workspace).where(Workspace.organization_id == org_id)
    if active_only:
        q = q.where(Workspace.is_active.is_(True))
    q = q.order_by(Workspace.is_default.desc(), Workspace.name).offset(skip).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_workspace(
    db: AsyncSession, org_id: int, workspace_id: int,
) -> Workspace | None:
    ws = await db.get(Workspace, workspace_id)
    if ws is None or ws.organization_id != org_id:
        return None
    return ws


async def get_default_workspace(db: AsyncSession, org_id: int) -> Workspace | None:
    q = (
        select(Workspace)
        .where(Workspace.organization_id == org_id, Workspace.is_default.is_(True))
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def ensure_default_workspace(db: AsyncSession, org_id: int) -> Workspace:
    """Return the default workspace for an org, creating it if missing."""
    ws = await get_default_workspace(db, org_id)
    if ws is not None:
        return ws
    ws = Workspace(
        organization_id=org_id,
        name="Default",
        slug="default",
        workspace_type="general",
        is_default=True,
    )
    db.add(ws)
    await db.flush()
    return ws


async def create_workspace(
    db: AsyncSession, org_id: int, data: WorkspaceCreate,
) -> Workspace:
    ws = Workspace(
        organization_id=org_id,
        name=data.name,
        slug=data.slug,
        workspace_type=data.workspace_type,
        description=data.description,
    )
    db.add(ws)
    await db.flush()
    return ws


async def update_workspace(
    db: AsyncSession, org_id: int, workspace_id: int, data: WorkspaceUpdate,
) -> Workspace | None:
    ws = await get_workspace(db, org_id, workspace_id)
    if ws is None:
        return None
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(ws, field, val)
    await db.flush()
    return ws


# ── Membership ───────────────────────────────────────────────────────────────

async def list_members(
    db: AsyncSession, workspace_id: int,
) -> list[WorkspaceMembership]:
    q = (
        select(WorkspaceMembership)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(WorkspaceMembership.joined_at)
    )
    return list((await db.execute(q)).scalars().all())


async def add_member(
    db: AsyncSession, workspace_id: int, user_id: int, role_override: str | None = None,
) -> WorkspaceMembership:
    m = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=user_id,
        role_override=role_override,
    )
    db.add(m)
    await db.flush()
    return m


async def remove_member(
    db: AsyncSession, workspace_id: int, user_id: int,
) -> bool:
    q = select(WorkspaceMembership).where(
        WorkspaceMembership.workspace_id == workspace_id,
        WorkspaceMembership.user_id == user_id,
    )
    m = (await db.execute(q)).scalar_one_or_none()
    if m is None:
        return False
    await db.delete(m)
    await db.flush()
    return True


async def user_can_access_workspace(
    db: AsyncSession,
    *,
    workspace_id: int,
    org_id: int,
    user_id: int,
    actor_role: str,
) -> bool:
    """
    Return True when the actor may operate within workspace_id.

    Rules:
    - Workspace must belong to the actor org and be active.
    - CEO/ADMIN can access any active workspace in org.
    - Default workspace is org-wide for backward compatibility.
    - Other roles require an active workspace_membership row.
    """
    ws = await get_workspace(db, org_id=org_id, workspace_id=workspace_id)
    if ws is None or not bool(getattr(ws, "is_active", False)):
        return False

    role = str(actor_role or "").upper()
    if role in {"CEO", "ADMIN"}:
        return True
    if bool(getattr(ws, "is_default", False)):
        return True

    membership = (
        await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    return membership is not None
