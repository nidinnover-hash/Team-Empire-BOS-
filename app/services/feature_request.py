"""Feedback / feature request service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_request import FeatureRequest


async def create_request(
    db: AsyncSession, *, organization_id: int, title: str,
    description: str | None = None, category: str | None = None,
    priority: str = "medium", submitted_by_user_id: int | None = None,
    contact_id: int | None = None,
) -> FeatureRequest:
    row = FeatureRequest(
        organization_id=organization_id, title=title,
        description=description, category=category,
        priority=priority, submitted_by_user_id=submitted_by_user_id,
        contact_id=contact_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_requests(
    db: AsyncSession, organization_id: int, *,
    status: str | None = None, category: str | None = None,
    sort_by: str = "votes",
) -> list[FeatureRequest]:
    q = select(FeatureRequest).where(FeatureRequest.organization_id == organization_id)
    if status:
        q = q.where(FeatureRequest.status == status)
    if category:
        q = q.where(FeatureRequest.category == category)
    if sort_by == "votes":
        q = q.order_by(FeatureRequest.votes.desc())
    else:
        q = q.order_by(FeatureRequest.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_request(db: AsyncSession, request_id: int, organization_id: int) -> FeatureRequest | None:
    q = select(FeatureRequest).where(FeatureRequest.id == request_id, FeatureRequest.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_request(db: AsyncSession, request_id: int, organization_id: int, **kwargs) -> FeatureRequest | None:
    row = await get_request(db, request_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def vote(db: AsyncSession, request_id: int, organization_id: int) -> FeatureRequest | None:
    row = await get_request(db, request_id, organization_id)
    if not row:
        return None
    row.votes += 1
    await db.commit()
    await db.refresh(row)
    return row


async def get_stats(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(FeatureRequest.status, func.count(FeatureRequest.id))
        .where(FeatureRequest.organization_id == organization_id)
        .group_by(FeatureRequest.status)
    )).all()
    return {status: count for status, count in rows}
