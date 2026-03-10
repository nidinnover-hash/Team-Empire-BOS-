"""Territory assignment service."""
from __future__ import annotations

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.territory_assignment import TerritoryAssignment


async def create_assignment(db: AsyncSession, *, organization_id: int, **kw) -> TerritoryAssignment:
    row = TerritoryAssignment(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_assignments(db: AsyncSession, org_id: int, *, territory_id: int | None = None, user_id: int | None = None) -> list[TerritoryAssignment]:
    q = select(TerritoryAssignment).where(TerritoryAssignment.organization_id == org_id)
    if territory_id:
        q = q.where(TerritoryAssignment.territory_id == territory_id)
    if user_id:
        q = q.where(TerritoryAssignment.user_id == user_id)
    q = q.order_by(TerritoryAssignment.assigned_at.desc())
    return list((await db.execute(q)).scalars().all())


async def delete_assignment(db: AsyncSession, assignment_id: int, org_id: int) -> bool:
    result = await db.execute(delete(TerritoryAssignment).where(TerritoryAssignment.id == assignment_id, TerritoryAssignment.organization_id == org_id))
    await db.commit()
    return (result.rowcount or 0) > 0


async def get_coverage(db: AsyncSession, org_id: int) -> dict:
    assignments = await list_assignments(db, org_id)
    territories = set(a.territory_id for a in assignments)
    users = set(a.user_id for a in assignments)
    total_quota = sum(a.quota for a in assignments)
    total_revenue = sum(a.current_revenue for a in assignments)
    return {
        "territories_covered": len(territories),
        "reps_assigned": len(users),
        "total_quota": round(total_quota, 2),
        "total_revenue": round(total_revenue, 2),
        "attainment_pct": round(total_revenue / max(total_quota, 1) * 100, 1),
    }
