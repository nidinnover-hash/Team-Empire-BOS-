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


async def create_organization(db: AsyncSession, name: str, slug: str) -> Organization:
    org = Organization(name=name, slug=slug, policy_json=json.dumps(default_policy_config()))
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
    await db.commit()
    await db.refresh(org)
    return current
