"""Deal rotation / round-robin service."""
from __future__ import annotations

import json

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal_rotation import RotationQueue, RotationAssignment


async def create_queue(
    db: AsyncSession, *, organization_id: int, name: str,
    user_ids: list[int] | None = None, is_active: bool = True,
) -> RotationQueue:
    row = RotationQueue(
        organization_id=organization_id, name=name,
        user_ids_json=json.dumps(user_ids or []),
        is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_queues(
    db: AsyncSession, organization_id: int, *,
    is_active: bool | None = None,
) -> list[RotationQueue]:
    q = select(RotationQueue).where(RotationQueue.organization_id == organization_id)
    if is_active is not None:
        q = q.where(RotationQueue.is_active == is_active)
    q = q.order_by(RotationQueue.name)
    return list((await db.execute(q)).scalars().all())


async def get_queue(db: AsyncSession, queue_id: int, organization_id: int) -> RotationQueue | None:
    q = select(RotationQueue).where(RotationQueue.id == queue_id, RotationQueue.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_queue(db: AsyncSession, queue_id: int, organization_id: int, **kwargs) -> RotationQueue | None:
    row = await get_queue(db, queue_id, organization_id)
    if not row:
        return None
    if "user_ids" in kwargs:
        kwargs["user_ids_json"] = json.dumps(kwargs.pop("user_ids") or [])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_queue(db: AsyncSession, queue_id: int, organization_id: int) -> bool:
    row = await get_queue(db, queue_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def assign_next(
    db: AsyncSession, *, organization_id: int, queue_id: int, deal_id: int,
) -> RotationAssignment | None:
    queue = await get_queue(db, queue_id, organization_id)
    if not queue or not queue.is_active:
        return None
    user_ids = json.loads(queue.user_ids_json)
    if not user_ids:
        return None
    assigned_user_id = user_ids[queue.current_index % len(user_ids)]
    assignment = RotationAssignment(
        organization_id=organization_id, queue_id=queue_id,
        deal_id=deal_id, assigned_user_id=assigned_user_id,
    )
    db.add(assignment)
    queue.current_index = (queue.current_index + 1) % len(user_ids)
    queue.total_assignments += 1
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def list_assignments(
    db: AsyncSession, organization_id: int, queue_id: int,
    *, limit: int = 50,
) -> list[RotationAssignment]:
    q = (
        select(RotationAssignment)
        .where(RotationAssignment.organization_id == organization_id, RotationAssignment.queue_id == queue_id)
        .order_by(RotationAssignment.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())


async def get_fairness(db: AsyncSession, organization_id: int, queue_id: int) -> dict:
    rows = (await db.execute(
        select(RotationAssignment.assigned_user_id, func.count(RotationAssignment.id))
        .where(RotationAssignment.organization_id == organization_id, RotationAssignment.queue_id == queue_id)
        .group_by(RotationAssignment.assigned_user_id)
    )).all()
    distribution = {uid: cnt for uid, cnt in rows}
    total = sum(distribution.values()) if distribution else 0
    return {"distribution": distribution, "total": total}
