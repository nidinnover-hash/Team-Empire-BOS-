from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org_membership import OrganizationMembership


async def list_memberships(db: AsyncSession, organization_id: int) -> list[OrganizationMembership]:
    result = await db.execute(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active.is_(True),
        )
        .order_by(OrganizationMembership.created_at.asc())
    )
    return list(result.scalars().all())


async def get_membership(
    db: AsyncSession,
    *,
    organization_id: int,
    user_id: int,
) -> OrganizationMembership | None:
    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    return cast(OrganizationMembership | None, result.scalar_one_or_none())


async def upsert_membership(
    db: AsyncSession,
    *,
    organization_id: int,
    user_id: int,
    role: str,
) -> OrganizationMembership:
    existing = await get_membership(db, organization_id=organization_id, user_id=user_id)
    now = datetime.now(UTC)
    if existing is not None:
        existing.role = role
        existing.is_active = True
        existing.updated_at = now
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return existing
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership
