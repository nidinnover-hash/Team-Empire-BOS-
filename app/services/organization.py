from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


async def get_organization_by_slug(db: AsyncSession, slug: str) -> Organization | None:
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    return result.scalar_one_or_none()


async def get_organization_by_id(db: AsyncSession, organization_id: int) -> Organization | None:
    result = await db.execute(select(Organization).where(Organization.id == organization_id))
    return result.scalar_one_or_none()


async def list_organizations(db: AsyncSession, limit: int = 200) -> list[Organization]:
    result = await db.execute(select(Organization).order_by(Organization.id).limit(limit))
    return list(result.scalars().all())


async def create_organization(db: AsyncSession, name: str, slug: str) -> Organization:
    org = Organization(name=name, slug=slug)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


async def update_organization(
    db: AsyncSession,
    organization_id: int,
    name: str | None = None,
    slug: str | None = None,
) -> Organization | None:
    org = await get_organization_by_id(db, organization_id)
    if org is None:
        return None
    if name is not None:
        org.name = name
    if slug is not None:
        org.slug = slug
    await db.commit()
    await db.refresh(org)
    return org


async def ensure_default_organization(db: AsyncSession) -> Organization:
    existing = await get_organization_by_slug(db, "default")
    if existing is not None:
        return existing
    org = Organization(name="Default Organization", slug="default")
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org
