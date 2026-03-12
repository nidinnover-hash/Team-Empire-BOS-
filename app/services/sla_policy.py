"""SLA policy service — CRUD and breach detection."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sla_policy import SlaBreach, SlaPolicy


async def create_policy(db: AsyncSession, organization_id: int, **kwargs) -> SlaPolicy:
    policy = SlaPolicy(organization_id=organization_id, **kwargs)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def list_policies(db: AsyncSession, organization_id: int, active_only: bool = True) -> list[SlaPolicy]:
    q = select(SlaPolicy).where(SlaPolicy.organization_id == organization_id)
    if active_only:
        q = q.where(SlaPolicy.is_active.is_(True))
    result = await db.execute(q.order_by(SlaPolicy.id))
    return list(result.scalars().all())


async def update_policy(db: AsyncSession, policy_id: int, organization_id: int, **kwargs) -> SlaPolicy | None:
    result = await db.execute(
        select(SlaPolicy).where(SlaPolicy.id == policy_id, SlaPolicy.organization_id == organization_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(policy, k):
            setattr(policy, k, v)
    await db.commit()
    await db.refresh(policy)
    return policy


async def delete_policy(db: AsyncSession, policy_id: int, organization_id: int) -> bool:
    result = await db.execute(
        select(SlaPolicy).where(SlaPolicy.id == policy_id, SlaPolicy.organization_id == organization_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        return False
    policy.is_active = False
    await db.commit()
    return True


async def record_breach(
    db: AsyncSession, organization_id: int, policy_id: int,
    entity_type: str, entity_id: int, breach_type: str,
) -> SlaBreach:
    breach = SlaBreach(
        organization_id=organization_id, policy_id=policy_id,
        entity_type=entity_type, entity_id=entity_id, breach_type=breach_type,
    )
    db.add(breach)
    await db.commit()
    await db.refresh(breach)
    return breach


async def list_breaches(
    db: AsyncSession, organization_id: int, entity_type: str | None = None, limit: int = 50,
) -> list[SlaBreach]:
    q = select(SlaBreach).where(SlaBreach.organization_id == organization_id)
    if entity_type:
        q = q.where(SlaBreach.entity_type == entity_type)
    result = await db.execute(q.order_by(SlaBreach.breached_at.desc()).limit(limit))
    return list(result.scalars().all())


async def check_entity_sla(
    db: AsyncSession, organization_id: int, entity_type: str,
    target_field: str, target_value: str, created_at: datetime,
) -> list[dict]:
    """Check if an entity is breaching any SLA policies."""
    policies = await list_policies(db, organization_id)
    now = datetime.now(UTC)
    violations = []
    for p in policies:
        if p.entity_type != entity_type or p.target_field != target_field or p.target_value != target_value:
            continue
        age_hours = (now - created_at).total_seconds() / 3600
        if p.response_hours and age_hours > p.response_hours:
            violations.append({"policy_id": p.id, "name": p.name, "type": "response", "limit_hours": p.response_hours, "actual_hours": round(age_hours, 1)})
        if p.resolution_hours and age_hours > p.resolution_hours:
            violations.append({"policy_id": p.id, "name": p.name, "type": "resolution", "limit_hours": p.resolution_hours, "actual_hours": round(age_hours, 1)})
    return violations
