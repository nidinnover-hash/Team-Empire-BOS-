from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import feature_flags


async def quotes_enabled(db: AsyncSession | None = None, organization_id: int | None = None) -> bool:
    if db is None or organization_id is None:
        return bool(settings.FEATURE_QUOTES)
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="quotes",
        default=bool(settings.FEATURE_QUOTES),
    )


async def playbooks_enabled(db: AsyncSession | None = None, organization_id: int | None = None) -> bool:
    if db is None or organization_id is None:
        return bool(settings.FEATURE_PLAYBOOKS)
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="playbooks",
        default=bool(settings.FEATURE_PLAYBOOKS),
    )


async def surveys_enabled(db: AsyncSession | None = None, organization_id: int | None = None) -> bool:
    if db is None or organization_id is None:
        return bool(settings.FEATURE_SURVEYS)
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="surveys",
        default=bool(settings.FEATURE_SURVEYS),
    )
