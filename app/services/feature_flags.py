from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import organization as organization_service


def _to_bucket(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _normalize_org_flag_name(flag_name: str) -> str:
    return str(flag_name or "").strip().lower().removeprefix("feature_")


def _settings_feature_key(flag_name: str) -> str:
    normalized = _normalize_org_flag_name(flag_name).upper()
    return f"FEATURE_{normalized}"


def _global_feature_default(flag_name: str, default: bool = False) -> bool:
    key = _settings_feature_key(flag_name)
    raw = getattr(settings, key, default)
    return bool(raw)


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


async def get_effective_flag_config(
    db: AsyncSession,
    *,
    organization_id: int,
    flag_name: str,
    default: bool = False,
) -> dict[str, Any]:
    """
    Resolve a flag using org override first, then global FEATURE_* setting fallback.
    """
    org_key = _normalize_org_flag_name(flag_name)
    global_enabled = _global_feature_default(org_key, default=default)
    _, flags = await organization_service.get_feature_flags(db, organization_id)
    raw = flags.get(org_key)
    if not isinstance(raw, dict):
        return {"enabled": global_enabled, "rollout_percentage": 100 if global_enabled else 0}

    enabled = bool(raw.get("enabled", global_enabled))
    rollout_raw = raw.get("rollout_percentage", 100 if enabled else 0)
    try:
        rollout = int(rollout_raw)
    except (TypeError, ValueError):
        rollout = 100 if enabled else 0
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


async def is_effective_feature_enabled(
    db: AsyncSession,
    *,
    organization_id: int,
    flag_name: str,
    subject_key: str | None = None,
    default: bool = False,
) -> bool:
    """
    Backward-compatible "effective" resolver:
    org policy override -> global FEATURE_* default -> explicit default arg.
    """
    config = await get_effective_flag_config(
        db,
        organization_id=organization_id,
        flag_name=flag_name,
        default=default,
    )
    if not bool(config.get("enabled", False)):
        return False

    rollout = int(config.get("rollout_percentage", 0) or 0)
    if rollout >= 100:
        return True
    if rollout <= 0:
        return False
    if not subject_key:
        return True

    bucket = _to_bucket(f"{organization_id}:{_normalize_org_flag_name(flag_name)}:{subject_key}")
    return bucket < rollout
