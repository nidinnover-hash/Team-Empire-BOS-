"""Lead scoring rules engine service."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_score_rule import LeadScoreRule


async def create_rule(
    db: AsyncSession, *, organization_id: int, name: str,
    rule_type: str = "field", field_name: str | None = None,
    operator: str | None = None, value: str | None = None,
    score_delta: int = 0, weight: float = 1.0,
    is_active: bool = True, conditions: dict | None = None,
) -> LeadScoreRule:
    row = LeadScoreRule(
        organization_id=organization_id, name=name,
        rule_type=rule_type, field_name=field_name,
        operator=operator, value=value, score_delta=score_delta,
        weight=weight, is_active=is_active,
        conditions_json=json.dumps(conditions or {}),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_rules(
    db: AsyncSession, organization_id: int, *,
    rule_type: str | None = None, is_active: bool | None = None,
) -> list[LeadScoreRule]:
    q = select(LeadScoreRule).where(LeadScoreRule.organization_id == organization_id)
    if rule_type:
        q = q.where(LeadScoreRule.rule_type == rule_type)
    if is_active is not None:
        q = q.where(LeadScoreRule.is_active == is_active)
    q = q.order_by(LeadScoreRule.name)
    return list((await db.execute(q)).scalars().all())


async def get_rule(db: AsyncSession, rule_id: int, organization_id: int) -> LeadScoreRule | None:
    q = select(LeadScoreRule).where(LeadScoreRule.id == rule_id, LeadScoreRule.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_rule(db: AsyncSession, rule_id: int, organization_id: int, **kwargs) -> LeadScoreRule | None:
    row = await get_rule(db, rule_id, organization_id)
    if not row:
        return None
    if "conditions" in kwargs:
        kwargs["conditions_json"] = json.dumps(kwargs.pop("conditions") or {})
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_rule(db: AsyncSession, rule_id: int, organization_id: int) -> bool:
    row = await get_rule(db, rule_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def evaluate_rules(db: AsyncSession, organization_id: int, contact_data: dict) -> dict:
    rules = await list_rules(db, organization_id, is_active=True)
    total_score = 0
    matched = []
    for rule in rules:
        if rule.field_name and rule.field_name in contact_data:
            val = str(contact_data[rule.field_name])
            if (rule.operator == "equals" and val == rule.value) or (rule.operator == "contains" and rule.value and rule.value in val):
                delta = int(rule.score_delta * float(rule.weight))
                total_score += delta
                matched.append({"rule_id": rule.id, "name": rule.name, "delta": delta})
    return {"total_score": total_score, "matched_rules": matched}
