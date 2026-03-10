"""Deal dependency service."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal_dependency import DealDependency


async def create_dependency(db: AsyncSession, *, organization_id: int, **kw) -> DealDependency:
    row = DealDependency(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_dependencies(db: AsyncSession, org_id: int, deal_id: int) -> list[DealDependency]:
    q = select(DealDependency).where(
        DealDependency.organization_id == org_id,
        (DealDependency.deal_id == deal_id) | (DealDependency.depends_on_deal_id == deal_id),
    ).order_by(DealDependency.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def resolve_dependency(db: AsyncSession, dep_id: int, org_id: int) -> DealDependency | None:
    row = (await db.execute(select(DealDependency).where(DealDependency.id == dep_id, DealDependency.organization_id == org_id))).scalar_one_or_none()
    if not row:
        return None
    row.is_resolved = True
    row.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_dependency(db: AsyncSession, dep_id: int, org_id: int) -> bool:
    result = await db.execute(delete(DealDependency).where(DealDependency.id == dep_id, DealDependency.organization_id == org_id))
    await db.commit()
    return (result.rowcount or 0) > 0


async def get_blockers(db: AsyncSession, org_id: int, deal_id: int) -> list[DealDependency]:
    q = select(DealDependency).where(
        DealDependency.organization_id == org_id,
        DealDependency.deal_id == deal_id,
        DealDependency.dependency_type == "blocks",
        DealDependency.is_resolved == False,
    )
    return list((await db.execute(q)).scalars().all())
