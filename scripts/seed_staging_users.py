import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.models.organization import Organization
from app.models.registry import load_all_models
from app.models.user import User


def _env_required(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


async def _ensure_org(session, *, name: str, slug: str) -> Organization:
    org = await session.scalar(select(Organization).where(Organization.slug == slug))
    if org:
        if org.name != name:
            org.name = name
        return org

    by_name = await session.scalar(select(Organization).where(Organization.name == name))
    if by_name:
        if by_name.slug != slug:
            by_name.slug = slug
        return by_name

    org = Organization(name=name, slug=slug)
    session.add(org)
    await session.flush()
    return org


async def _ensure_user(
    session,
    *,
    org_id: int,
    email: str,
    password: str,
    role: str,
    name: str,
) -> User:
    email_norm = email.lower().strip()
    user = await session.scalar(select(User).where(User.email == email_norm))
    if user:
        user.organization_id = org_id
        user.role = role
        user.name = name
        user.is_active = True
        if password:
            user.password_hash = hash_password(password)
        return user

    user = User(
        organization_id=org_id,
        email=email_norm,
        name=name,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        token_version=1,
        is_super_admin=False,
    )
    session.add(user)
    await session.flush()
    return user


async def main() -> None:
    load_dotenv(".env.staging")
    db_url = _env_required("STAGING_PGCONN")
    org1_email = _env_required("STAGING_ORG1_EMAIL")
    org1_password = _env_required("STAGING_ORG1_PASSWORD")
    org1_slug = _env_required("STAGING_ORG1_ID")
    org2_email = _env_required("STAGING_ORG2_EMAIL")
    org2_password = _env_required("STAGING_ORG2_PASSWORD")
    org2_slug = _env_required("STAGING_ORG2_ID")

    load_all_models()
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        org1 = await _ensure_org(session, name="Team Empire Org", slug=org1_slug)
        org2 = await _ensure_org(session, name="Team Empire India", slug=org2_slug)

        await _ensure_user(
            session,
            org_id=org1.id,
            email=org1_email,
            password=org1_password,
            role="CEO",
            name="Staging Admin",
        )
        await _ensure_user(
            session,
            org_id=org2.id,
            email=org2_email,
            password=org2_password,
            role="ADMIN",
            name="Staging India Admin",
        )
        await session.commit()

    await engine.dispose()
    print("Staging seed complete (idempotent).")


if __name__ == "__main__":
    asyncio.run(main())
