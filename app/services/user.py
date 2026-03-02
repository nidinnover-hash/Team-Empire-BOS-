from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email.lower().strip())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    user = User(
        organization_id=data.organization_id,
        name=data.name,
        email=data.email.lower().strip(),
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession, organization_id: int, limit: int = 100, offset: int = 0
) -> list[User]:
    result = await db.execute(
        select(User)
        .where(User.organization_id == organization_id)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


VALID_ROLES = {
    "CEO", "ADMIN", "MANAGER", "STAFF", "OWNER",
    "TECH_LEAD", "OPS_MANAGER", "DEVELOPER", "VIEWER",
}


async def update_user_role(
    db: AsyncSession, user_id: int, organization_id: int, new_role: str,
) -> User | None:
    if new_role not in VALID_ROLES:
        return None
    user = await get_user_by_id(db, user_id)
    if user is None or user.organization_id != organization_id:
        return None
    user.role = new_role
    await db.commit()
    await db.refresh(user)
    return user


async def toggle_user_active(
    db: AsyncSession, user_id: int, organization_id: int, is_active: bool,
) -> User | None:
    user = await get_user_by_id(db, user_id)
    if user is None or user.organization_id != organization_id:
        return None
    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    return user


async def ensure_default_user(db: AsyncSession, organization_id: int) -> None:
    demo = await get_user_by_email(db, settings.ADMIN_EMAIL)
    if demo is not None:
        return
    db.add(
        User(
            organization_id=organization_id,
            name=settings.ADMIN_NAME,
            email=settings.ADMIN_EMAIL.lower().strip(),
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            role="CEO",
            is_active=True,
        )
    )
    await db.commit()
