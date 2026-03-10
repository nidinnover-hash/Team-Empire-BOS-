"""Territory management service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.territory import Territory


async def create_territory(
    db: AsyncSession, *, organization_id: int, name: str,
    region: str | None = None, industry: str | None = None,
    description: str | None = None, assigned_user_id: int | None = None,
) -> Territory:
    row = Territory(
        organization_id=organization_id, name=name,
        region=region, industry=industry, description=description,
        assigned_user_id=assigned_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_territories(
    db: AsyncSession, organization_id: int, *,
    region: str | None = None, assigned_user_id: int | None = None,
) -> list[Territory]:
    q = select(Territory).where(Territory.organization_id == organization_id)
    if region:
        q = q.where(Territory.region == region)
    if assigned_user_id is not None:
        q = q.where(Territory.assigned_user_id == assigned_user_id)
    q = q.order_by(Territory.name)
    return list((await db.execute(q)).scalars().all())


async def get_territory(db: AsyncSession, territory_id: int, organization_id: int) -> Territory | None:
    q = select(Territory).where(Territory.id == territory_id, Territory.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_territory(db: AsyncSession, territory_id: int, organization_id: int, **kwargs) -> Territory | None:
    row = await get_territory(db, territory_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_territory(db: AsyncSession, territory_id: int, organization_id: int) -> bool:
    row = await get_territory(db, territory_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
