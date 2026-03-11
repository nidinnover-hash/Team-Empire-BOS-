"""Workspace permission service — manage memberships and check access."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership


async def list_workspaces(
    db: AsyncSession, organization_id: int,
) -> list[Workspace]:
    result = await db.execute(
        select(Workspace).where(
            Workspace.organization_id == organization_id,
            Workspace.is_active.is_(True),
        ).order_by(Workspace.id)
    )
    return list(result.scalars().all())


async def get_user_workspaces(
    db: AsyncSession, user_id: int, organization_id: int,
) -> list[dict]:
    """Return workspaces the user is a member of, with effective roles."""
    result = await db.execute(
        select(Workspace, WorkspaceMembership)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(
            Workspace.organization_id == organization_id,
            Workspace.is_active.is_(True),
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.is_active.is_(True),
        )
    )
    rows = result.all()

    # Also get user's org-level role
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    org_role = user.role if user else "STAFF"

    workspaces = []
    for ws, membership in rows:
        workspaces.append({
            "workspace_id": ws.id,
            "workspace_name": ws.name,
            "workspace_slug": ws.slug,
            "workspace_type": ws.workspace_type,
            "is_default": ws.is_default,
            "effective_role": membership.role_override or org_role,
            "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
        })
    return workspaces


async def add_member(
    db: AsyncSession, workspace_id: int, user_id: int, role_override: str | None = None,
) -> WorkspaceMembership:
    """Add a user to a workspace."""
    # Check if already a member
    existing = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    membership = existing.scalar_one_or_none()
    if membership:
        membership.is_active = True
        membership.role_override = role_override
        await db.commit()
        await db.refresh(membership)
        return membership

    membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=user_id,
        role_override=role_override,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership


async def remove_member(
    db: AsyncSession, workspace_id: int, user_id: int,
) -> bool:
    """Deactivate a user's membership in a workspace."""
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return False
    membership.is_active = False
    await db.commit()
    return True


async def list_members(
    db: AsyncSession, workspace_id: int,
) -> list[dict]:
    """List active members of a workspace."""
    result = await db.execute(
        select(WorkspaceMembership, User)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.is_active.is_(True),
        )
    )
    rows = result.all()
    return [
        {
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
            "org_role": user.role,
            "workspace_role": membership.role_override or user.role,
            "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
        }
        for membership, user in rows
    ]


async def check_access(
    db: AsyncSession, workspace_id: int, user_id: int,
) -> dict | None:
    """Check if a user has access to a workspace. Returns role info or None."""
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.is_active.is_(True),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return None

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    org_role = user.role if user else "STAFF"

    return {
        "has_access": True,
        "effective_role": membership.role_override or org_role,
        "workspace_id": workspace_id,
    }
