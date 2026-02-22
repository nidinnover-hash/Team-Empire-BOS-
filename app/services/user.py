from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    user = User(
        organization_id=data.organization_id,
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession, organization_id: int, limit: int = 100
) -> list[User]:
    result = await db.execute(
        select(User)
        .where(User.organization_id == organization_id)
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def ensure_default_user(db: AsyncSession, organization_id: int = 1) -> None:
    demo = await get_user_by_email(db, "demo@ai.com")
    if demo is not None:
        return
    db.add(
        User(
            organization_id=organization_id,
            name="Demo Admin",
            email="demo@ai.com",
            password_hash=hash_password("demo"),
            role="CEO",
            is_active=True,
        )
    )
    await db.commit()
