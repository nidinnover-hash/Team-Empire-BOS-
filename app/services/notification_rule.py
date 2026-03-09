"""Notification rules engine — match events to notification rules."""
from __future__ import annotations

import fnmatch
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_rule import NotificationRule

logger = logging.getLogger(__name__)


async def create_rule(
    db: AsyncSession, organization_id: int, **kwargs,
) -> NotificationRule:
    rule = NotificationRule(organization_id=organization_id, **kwargs)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_rules(
    db: AsyncSession, organization_id: int, active_only: bool = True,
) -> list[NotificationRule]:
    q = select(NotificationRule).where(
        NotificationRule.organization_id == organization_id,
    )
    if active_only:
        q = q.where(NotificationRule.is_active.is_(True))
    q = q.order_by(NotificationRule.id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_rule(
    db: AsyncSession, rule_id: int, organization_id: int, **kwargs,
) -> NotificationRule | None:
    result = await db.execute(
        select(NotificationRule).where(
            NotificationRule.id == rule_id,
            NotificationRule.organization_id == organization_id,
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
        select(NotificationRule).where(
            NotificationRule.id == rule_id,
            NotificationRule.organization_id == organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return False
    await db.delete(rule)
    await db.commit()
    return True


def match_event_to_rules(
    event_type: str, rules: list[NotificationRule],
) -> list[NotificationRule]:
    """Return rules whose event_type_pattern matches the given event_type."""
    matched = []
    for rule in rules:
        if fnmatch.fnmatch(event_type, rule.event_type_pattern):
            matched.append(rule)
    return matched


async def evaluate_event(
    db: AsyncSession, organization_id: int, event_type: str,
) -> list[dict]:
    """Evaluate an event against all active rules and return matched rule info."""
    rules = await list_rules(db, organization_id, active_only=True)
    matched = match_event_to_rules(event_type, rules)
    return [
        {
            "rule_id": r.id,
            "name": r.name,
            "severity": r.severity,
            "channel": r.channel,
            "target_roles": r.target_roles,
            "target_user_id": r.target_user_id,
        }
        for r in matched
    ]
