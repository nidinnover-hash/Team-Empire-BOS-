"""Goal cascade service — link company goals to team goals to quotas."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal_cascade import GoalCascadeLink


async def create_link(
    db: AsyncSession, *, organization_id: int,
    parent_type: str, parent_id: int,
    child_type: str, child_id: int,
    weight: float = 1.0, notes: str | None = None,
) -> GoalCascadeLink:
    row = GoalCascadeLink(
        organization_id=organization_id,
        parent_type=parent_type, parent_id=parent_id,
        child_type=child_type, child_id=child_id,
        weight=weight, notes=notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_links(
    db: AsyncSession, organization_id: int, *,
    parent_type: str | None = None, parent_id: int | None = None,
) -> list[GoalCascadeLink]:
    q = select(GoalCascadeLink).where(GoalCascadeLink.organization_id == organization_id)
    if parent_type:
        q = q.where(GoalCascadeLink.parent_type == parent_type)
    if parent_id is not None:
        q = q.where(GoalCascadeLink.parent_id == parent_id)
    q = q.order_by(GoalCascadeLink.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_children(db: AsyncSession, organization_id: int, parent_type: str, parent_id: int) -> list[GoalCascadeLink]:
    q = select(GoalCascadeLink).where(
        GoalCascadeLink.organization_id == organization_id,
        GoalCascadeLink.parent_type == parent_type,
        GoalCascadeLink.parent_id == parent_id,
    ).order_by(GoalCascadeLink.weight.desc())
    return list((await db.execute(q)).scalars().all())


async def get_parents(db: AsyncSession, organization_id: int, child_type: str, child_id: int) -> list[GoalCascadeLink]:
    q = select(GoalCascadeLink).where(
        GoalCascadeLink.organization_id == organization_id,
        GoalCascadeLink.child_type == child_type,
        GoalCascadeLink.child_id == child_id,
    ).order_by(GoalCascadeLink.weight.desc())
    return list((await db.execute(q)).scalars().all())


async def delete_link(db: AsyncSession, link_id: int, organization_id: int) -> bool:
    q = select(GoalCascadeLink).where(
        GoalCascadeLink.id == link_id,
        GoalCascadeLink.organization_id == organization_id,
    )
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def get_tree(db: AsyncSession, organization_id: int, root_type: str, root_id: int) -> dict:
    """Build a cascade tree starting from root."""
    children = await get_children(db, organization_id, root_type, root_id)
    result = {
        "type": root_type, "id": root_id, "children": [],
    }
    for link in children:
        child_tree = await get_tree(db, organization_id, link.child_type, link.child_id)
        child_tree["weight"] = link.weight
        child_tree["link_id"] = link.id
        result["children"].append(child_tree)
    return result
