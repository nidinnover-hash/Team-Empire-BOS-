from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lead_routing import EMPIRE_DIGITAL_COMPANY_ID, normalize_lead_type
from app.models.lead_routing_rule import LeadRoutingRule
from app.models.organization import Organization
from app.schemas.lead_routing_rule import LeadRoutingRuleCreate, LeadRoutingRuleUpdate


async def list_rules(
    db: AsyncSession,
    *,
    owner_company_id: int = EMPIRE_DIGITAL_COMPANY_ID,
    active_only: bool = False,
) -> list[LeadRoutingRule]:
    query = select(LeadRoutingRule).where(
        LeadRoutingRule.owner_company_id == owner_company_id
    )
    if active_only:
        query = query.where(LeadRoutingRule.is_active.is_(True))
    query = query.order_by(LeadRoutingRule.priority.asc(), LeadRoutingRule.id.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_rule(
    db: AsyncSession,
    *,
    owner_company_id: int,
    actor_user_id: int,
    data: LeadRoutingRuleCreate,
) -> LeadRoutingRule:
    target_org = await db.get(Organization, int(data.target_company_id))
    if target_org is None:
        raise ValueError("target_company_not_found")
    normalized_lead_type = normalize_lead_type(data.lead_type)
    existing_result = await db.execute(
        select(LeadRoutingRule).where(
            LeadRoutingRule.owner_company_id == owner_company_id,
            LeadRoutingRule.lead_type == normalized_lead_type,
            LeadRoutingRule.priority == data.priority,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        if existing.target_company_id == data.target_company_id:
            if not existing.is_active:
                existing.is_active = True
                existing.updated_by_user_id = actor_user_id
                await db.commit()
                await db.refresh(existing)
            return existing
        raise ValueError("duplicate_priority_for_lead_type")
    rule = LeadRoutingRule(
        owner_company_id=owner_company_id,
        lead_type=normalized_lead_type,
        target_company_id=data.target_company_id,
        priority=data.priority,
        routing_reason=data.routing_reason,
        is_active=True,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_rule(
    db: AsyncSession,
    *,
    owner_company_id: int,
    actor_user_id: int,
    rule_id: int,
    data: LeadRoutingRuleUpdate,
) -> LeadRoutingRule | None:
    result = await db.execute(
        select(LeadRoutingRule).where(
            LeadRoutingRule.id == rule_id,
            LeadRoutingRule.owner_company_id == owner_company_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return None
    payload = data.model_dump(exclude_unset=True)
    if "target_company_id" in payload:
        target_org = await db.get(Organization, int(payload["target_company_id"]))
        if target_org is None:
            raise ValueError("target_company_not_found")
    if "priority" in payload:
        duplicate_result = await db.execute(
            select(LeadRoutingRule).where(
                LeadRoutingRule.owner_company_id == owner_company_id,
                LeadRoutingRule.lead_type == rule.lead_type,
                LeadRoutingRule.priority == int(payload["priority"]),
                LeadRoutingRule.id != rule.id,
            )
        )
        duplicate = duplicate_result.scalar_one_or_none()
        if duplicate is not None:
            raise ValueError("duplicate_priority_for_lead_type")
    for key, value in payload.items():
        setattr(rule, key, value)
    rule.updated_by_user_id = actor_user_id
    await db.commit()
    await db.refresh(rule)
    return rule


async def resolve_rule_target(
    db: AsyncSession,
    *,
    owner_company_id: int,
    lead_type: str,
) -> LeadRoutingRule | None:
    normalized = normalize_lead_type(lead_type)
    result = await db.execute(
        select(LeadRoutingRule).where(
            LeadRoutingRule.owner_company_id == owner_company_id,
            LeadRoutingRule.lead_type == normalized,
            LeadRoutingRule.is_active.is_(True),
        ).order_by(LeadRoutingRule.priority.asc(), LeadRoutingRule.id.asc()).limit(1)
    )
    return result.scalar_one_or_none()
