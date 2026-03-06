import json
from json import JSONDecodeError
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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


async def create_organization(
    db: AsyncSession,
    name: str,
    slug: str,
    *,
    parent_organization_id: int | None = None,
    country_code: str | None = None,
    branch_label: str | None = None,
) -> Organization:
    org = Organization(
        name=name,
        slug=slug,
        parent_organization_id=parent_organization_id,
        country_code=(country_code or "").upper() or None,
        branch_label=branch_label,
        policy_json=json.dumps(default_policy_config()),
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


async def update_organization(
    db: AsyncSession,
    organization_id: int,
    name: str | None = None,
    slug: str | None = None,
    parent_organization_id: int | None = None,
    country_code: str | None = None,
    branch_label: str | None = None,
    expected_config_version: int | None = None,
) -> Organization | None:
    org = await get_organization_by_id(db, organization_id)
    if org is None:
        return None
    if expected_config_version is not None and int(org.config_version) != int(expected_config_version):
        return None
    if name is not None:
        org.name = name
    if slug is not None:
        org.slug = slug
    if parent_organization_id is not None:
        org.parent_organization_id = parent_organization_id
    if country_code is not None:
        org.country_code = country_code.upper()
    if branch_label is not None:
        org.branch_label = branch_label
    org.config_version = int(org.config_version) + 1
    await db.commit()
    await db.refresh(org)
    return org


async def ensure_default_organization(db: AsyncSession) -> Organization:
    existing = await get_organization_by_slug(db, "default")
    if existing is not None:
        return existing
    org = Organization(name="Default Organization", slug="default", policy_json=json.dumps(default_policy_config()))
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


def default_policy_config() -> dict[str, Any]:
    return {
        "owner_emails": [e.strip().lower() for e in (settings.COMPLIANCE_OWNER_EMAILS or "").split(",") if e.strip()],
        "tech_lead_email": (settings.COMPLIANCE_TECH_LEAD_EMAIL or "").strip().lower(),
        "ops_manager_email": (settings.COMPLIANCE_OPS_MANAGER_EMAIL or "").strip().lower(),
        "dev_emails": [e.strip().lower() for e in (settings.COMPLIANCE_DEV_EMAILS or "").split(",") if e.strip()],
        "company_domain": (settings.COMPLIANCE_COMPANY_DOMAIN or "").strip().lower(),
        "allowed_personal_emails": [
            e.strip().lower() for e in (settings.COMPLIANCE_ALLOWED_PERSONAL_EMAILS or "").split(",") if e.strip()
        ],
        "allow_personal_owner_exceptions": bool(settings.COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS),
        "critical_github_repos": [x.strip().lower() for x in (settings.CRITICAL_GITHUB_REPOS or "").split(",") if x.strip()],
        "autonomy_policy": {
            "current_mode": "approved_execution",
            "allow_auto_approval": True,
            "min_readiness_for_auto_approval": 70,
            "min_readiness_for_approved_execution": 65,
            "min_readiness_for_autonomous": 90,
            "block_on_unread_high_alerts": True,
            "block_on_stale_integrations": True,
            "block_on_sla_breaches": True,
        },
        "autonomy_rollout": {
            "kill_switch": False,
            "pilot_org_ids": [],
            "max_actions_per_day": 250,
        },
        "feature_flags": {
            "trend_snapshots_enabled": True,
        },
        "command_center": {
            "weights": {
                "critical_tokens": 3,
                "warning_tokens": 1,
                "open_violations_high": 2,
                "open_violations_low": 1,
                "pending_approvals": 1,
                "unread_emails": 1,
                "unread_high_alerts_high": 2,
                "unread_high_alerts_low": 1,
                "sync_errors_high": 2,
                "sync_errors_low": 1,
                "webhook_failures_high": 2,
                "webhook_failures_low": 1,
            },
            "thresholds": {
                "warning_tokens_min": 3,
                "open_violations_high": 5,
                "pending_approvals_min": 10,
                "unread_emails_min": 50,
                "unread_high_alerts_high": 5,
                "sync_errors_high": 3,
                "webhook_failures_high": 10,
            },
            "levels": {
                "amber": 2,
                "red": 4,
            },
        },
        "empire_digital": {
            "sla": {
                "stale_unrouted_days": 3,
                "warning_stale_count": 3,
                "warning_unrouted_count": 8,
            },
        },
    }


async def get_policy_config(db: AsyncSession, organization_id: int) -> dict[str, Any]:
    org = await get_organization_by_id(db, organization_id)
    if org is None:
        return default_policy_config()
    raw = (org.policy_json or "").strip()
    if not raw:
        return default_policy_config()
    try:
        parsed = json.loads(raw)
    except (JSONDecodeError, TypeError, ValueError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    merged = default_policy_config()
    merged.update(parsed)
    return merged


async def update_policy_config(db: AsyncSession, organization_id: int, config: dict[str, Any]) -> dict[str, Any] | None:
    org = await get_organization_by_id(db, organization_id)
    if org is None:
        return None
    current = await get_policy_config(db, organization_id)
    current.update(config)
    org.policy_json = json.dumps(current)
    org.config_version = int(org.config_version) + 1
    await db.commit()
    await db.refresh(org)
    return current


def _parse_feature_flags(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    def _safe_rollout_percentage(raw_value: Any, default: int) -> int:
        try:
            if raw_value is None:
                return default
            return int(raw_value)
        except (TypeError, ValueError):
            return default

    raw_flags = config.get("feature_flags", {})
    if not isinstance(raw_flags, dict):
        return {}
    parsed: dict[str, dict[str, Any]] = {}
    for key, raw in raw_flags.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if isinstance(raw, dict):
            enabled = bool(raw.get("enabled", True))
            rollout_default = 100 if enabled else 0
            rollout = _safe_rollout_percentage(raw.get("rollout_percentage"), rollout_default)
        else:
            enabled = bool(raw)
            rollout = 100 if enabled else 0
        parsed[key.strip()] = {
            "enabled": enabled,
            "rollout_percentage": max(0, min(100, rollout)),
        }
    return parsed


async def get_feature_flags(db: AsyncSession, organization_id: int) -> tuple[int, dict[str, dict[str, Any]]]:
    org = await get_organization_by_id(db, organization_id)
    if org is None:
        return 1, {}
    config = await get_policy_config(db, organization_id)
    return int(org.config_version), _parse_feature_flags(config)


async def update_feature_flags(
    db: AsyncSession,
    organization_id: int,
    flags: dict[str, dict[str, Any]],
    *,
    expected_config_version: int | None = None,
) -> tuple[int, dict[str, dict[str, Any]]] | None:
    org = await get_organization_by_id(db, organization_id)
    if org is None:
        return None
    if expected_config_version is not None and int(org.config_version) != int(expected_config_version):
        return None
    current = await get_policy_config(db, organization_id)
    current["feature_flags"] = _parse_feature_flags({"feature_flags": flags})
    org.policy_json = json.dumps(current)
    org.config_version = int(org.config_version) + 1
    await db.commit()
    await db.refresh(org)
    return int(org.config_version), _parse_feature_flags(current)
