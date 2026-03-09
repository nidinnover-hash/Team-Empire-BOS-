"""Saved filter service — persist and retrieve named search queries."""
from __future__ import annotations

import json

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.saved_filter import SavedFilter


async def create_filter(
    db: AsyncSession, organization_id: int, user_id: int, **kwargs,
) -> SavedFilter:
    if "filters" in kwargs:
        kwargs["filters_json"] = json.dumps(kwargs.pop("filters"))
    sf = SavedFilter(organization_id=organization_id, user_id=user_id, **kwargs)
    db.add(sf)
    await db.commit()
    await db.refresh(sf)
    return sf


async def list_filters(
    db: AsyncSession, organization_id: int, user_id: int,
    entity_type: str | None = None,
) -> list[SavedFilter]:
    q = select(SavedFilter).where(
        SavedFilter.organization_id == organization_id,
        SavedFilter.is_active.is_(True),
        or_(SavedFilter.user_id == user_id, SavedFilter.is_shared.is_(True)),
    )
    if entity_type:
        q = q.where(SavedFilter.entity_type == entity_type)
    result = await db.execute(q.order_by(SavedFilter.name))
    return list(result.scalars().all())


async def update_filter(
    db: AsyncSession, filter_id: int, organization_id: int, user_id: int, **kwargs,
) -> SavedFilter | None:
    result = await db.execute(
        select(SavedFilter).where(
            SavedFilter.id == filter_id,
            SavedFilter.organization_id == organization_id,
            SavedFilter.user_id == user_id,
        )
    )
    sf = result.scalar_one_or_none()
    if not sf:
        return None
    if "filters" in kwargs:
        kwargs["filters_json"] = json.dumps(kwargs.pop("filters"))
    for k, v in kwargs.items():
        if v is not None and hasattr(sf, k):
            setattr(sf, k, v)
    await db.commit()
    await db.refresh(sf)
    return sf


async def delete_filter(
    db: AsyncSession, filter_id: int, organization_id: int, user_id: int,
) -> bool:
    result = await db.execute(
        select(SavedFilter).where(
            SavedFilter.id == filter_id,
            SavedFilter.organization_id == organization_id,
            SavedFilter.user_id == user_id,
        )
    )
    sf = result.scalar_one_or_none()
    if not sf:
        return False
    sf.is_active = False
    await db.commit()
    return True
