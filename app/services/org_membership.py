from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org_membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User


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
    return result.scalar_one_or_none()


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


async def list_user_memberships(
    db: AsyncSession,
    *,
    user_id: int,
) -> list[OrganizationMembership]:
    result = await db.execute(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active.is_(True),
        )
        .order_by(OrganizationMembership.created_at.asc())
    )
    return list(result.scalars().all())


async def list_user_accessible_orgs(
    db: AsyncSession,
    *,
    user: User,
) -> list[dict[str, object]]:
    roles_by_org: dict[int, str] = {int(user.organization_id): str(user.role)}
    memberships = await list_user_memberships(db, user_id=int(user.id))
    for membership in memberships:
        roles_by_org[int(membership.organization_id)] = str(membership.role)

    org_ids = sorted(roles_by_org.keys())
    result = await db.execute(
        select(Organization).where(Organization.id.in_(org_ids)).order_by(Organization.name.asc())
    )
    orgs = list(result.scalars().all())

    primary_org_id = int(user.organization_id)
    payload: list[dict[str, object]] = []
    for org in orgs:
        payload.append(
            {
                "id": int(org.id),
                "name": str(org.name),
                "slug": str(org.slug),
                "role": roles_by_org.get(int(org.id), str(user.role)),
                "is_primary": int(org.id) == primary_org_id,
            }
        )
    payload.sort(key=lambda item: (not bool(item["is_primary"]), str(item["name"]).lower()))
    return payload


async def get_user_role_for_org(
    db: AsyncSession,
    *,
    user: User,
    organization_id: int,
) -> str | None:
    if bool(getattr(user, "is_super_admin", False)):
        return str(user.role)
    if int(user.organization_id) == int(organization_id):
        return str(user.role)
    membership = await get_membership(
        db,
        organization_id=int(organization_id),
        user_id=int(user.id),
    )
    if membership is None or not bool(membership.is_active):
        return None
    return str(membership.role)
