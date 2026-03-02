from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import organization as organization_service


def _to_bucket(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


async def get_flag_config(
    db: AsyncSession,
    *,
    organization_id: int,
    flag_name: str,
) -> dict[str, Any]:
    _, flags = await organization_service.get_feature_flags(db, organization_id)
    raw = flags.get(flag_name)
    if not isinstance(raw, dict):
        return {"enabled": False, "rollout_percentage": 0}
    enabled = bool(raw.get("enabled", False))
    rollout_raw = raw.get("rollout_percentage", 0)
    try:
        rollout = int(rollout_raw)
    except (TypeError, ValueError):
        rollout = 0
    return {
        "enabled": enabled,
        "rollout_percentage": max(0, min(100, rollout)),
    }


async def is_feature_enabled(
    db: AsyncSession,
    *,
    organization_id: int,
    flag_name: str,
    subject_key: str | None = None,
) -> bool:
    config = await get_flag_config(db, organization_id=organization_id, flag_name=flag_name)
    if not bool(config.get("enabled", False)):
        return False

    rollout = int(config.get("rollout_percentage", 0) or 0)
    if rollout >= 100:
        return True
    if rollout <= 0:
        return False

    # Org-level rollout if no subject is provided.
    if not subject_key:
        return True
    bucket = _to_bucket(f"{organization_id}:{flag_name}:{subject_key}")
    return bucket < rollout
