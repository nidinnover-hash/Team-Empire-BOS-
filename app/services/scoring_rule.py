"""Contact scoring rules engine — evaluate and apply configurable lead scoring."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.scoring_rule import ScoringRule

logger = logging.getLogger(__name__)


async def create_rule(
    db: AsyncSession, organization_id: int, **kwargs,
) -> ScoringRule:
    rule = ScoringRule(organization_id=organization_id, **kwargs)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_rules(
    db: AsyncSession, organization_id: int, active_only: bool = True,
) -> list[ScoringRule]:
    q = select(ScoringRule).where(ScoringRule.organization_id == organization_id)
    if active_only:
        q = q.where(ScoringRule.is_active.is_(True))
    q = q.order_by(ScoringRule.id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_rule(
    db: AsyncSession, rule_id: int, organization_id: int, **kwargs,
) -> ScoringRule | None:
    result = await db.execute(
        select(ScoringRule).where(
            ScoringRule.id == rule_id,
            ScoringRule.organization_id == organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(rule, k):
            setattr(rule, k, v)
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(
    db: AsyncSession, rule_id: int, organization_id: int,
) -> bool:
    result = await db.execute(
        select(ScoringRule).where(
            ScoringRule.id == rule_id,
            ScoringRule.organization_id == organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return False
    await db.delete(rule)
    await db.commit()
    return True


def _match_rule(rule: ScoringRule, contact: Contact) -> bool:
    """Check if a single rule matches a contact."""
    field_val = getattr(contact, rule.field, None)
    if field_val is None:
        return rule.operator == "not_empty" and False  # not_empty on None = no match
    field_val = str(field_val).lower()
    rule_val = rule.value.lower()

    if rule.operator == "contains":
        return rule_val in field_val
    elif rule.operator == "equals":
        return field_val == rule_val
    elif rule.operator == "starts_with":
        return field_val.startswith(rule_val)
    elif rule.operator == "not_empty":
        return len(field_val.strip()) > 0
    return False


async def score_contact(
    db: AsyncSession, contact: Contact, organization_id: int,
) -> dict:
    """Evaluate all active rules against a contact and return score breakdown."""
    rules = await list_rules(db, organization_id, active_only=True)
    base_score = contact.lead_score or 0
    adjustments: list[dict] = []
    total_delta = 0

    for rule in rules:
        if _match_rule(rule, contact):
            adjustments.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "field": rule.field,
                "delta": rule.score_delta,
            })
            total_delta += rule.score_delta

    new_score = max(0, min(100, base_score + total_delta))
    return {
        "contact_id": contact.id,
        "previous_score": base_score,
        "new_score": new_score,
        "adjustments": adjustments,
        "rules_evaluated": len(rules),
    }


async def apply_scoring_to_contact(
    db: AsyncSession, contact_id: int, organization_id: int,
) -> dict | None:
    """Score a contact and persist the new lead_score."""
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.organization_id == organization_id,
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        return None

    score_result = await score_contact(db, contact, organization_id)
    contact.lead_score = score_result["new_score"]
    contact.updated_at = datetime.now(UTC)
    await db.commit()
    return score_result
