"""API key generation, validation, and lifecycle management."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey

_PREFIX = "nbos_"


def _generate_key() -> tuple[str, str, str]:
    """Generate API key. Returns (full_key, prefix, key_hash)."""
    raw = secrets.token_hex(32)
    full_key = f"{_PREFIX}{raw}"
    prefix = full_key[:12]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, prefix, key_hash


async def create_api_key(
    db: AsyncSession,
    *,
    organization_id: int,
    user_id: int,
    name: str,
    scopes: str = "*",
    expires_in_days: int | None = None,
) -> tuple[ApiKey, str]:
    """Create a new API key. Returns (ApiKey, full_key_plaintext)."""
    full_key, prefix, key_hash = _generate_key()
    expires_at = (
        datetime.now(UTC) + timedelta(days=expires_in_days)
        if expires_in_days
        else None
    )
    api_key = ApiKey(
        organization_id=organization_id,
        user_id=user_id,
        name=name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key, full_key


async def list_api_keys(
    db: AsyncSession,
    organization_id: int,
    user_id: int,
    *,
    limit: int = 50,
) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey)
        .where(
            ApiKey.organization_id == organization_id,
            ApiKey.user_id == user_id,
        )
        .order_by(ApiKey.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def revoke_api_key(
    db: AsyncSession,
    key_id: int,
    organization_id: int,
    user_id: int,
) -> bool:
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == organization_id,
            ApiKey.user_id == user_id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        return False
    key.is_active = False
    await db.commit()
    return True


async def validate_api_key(db: AsyncSession, raw_key: str) -> ApiKey | None:
    """Validate an API key string. Returns ApiKey if valid, None otherwise."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return None
    if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
        return None
    api_key.last_used_at = datetime.now(UTC)
    await db.commit()
    return api_key
