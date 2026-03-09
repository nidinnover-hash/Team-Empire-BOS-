"""Contact score decay service — manage decay rules and simulate runs."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.score_decay import ScoreDecayRule


async def create_rule(db: AsyncSession, organization_id: int, **kwargs) -> ScoreDecayRule:
    rule = ScoreDecayRule(organization_id=organization_id, **kwargs)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_rules(
    db: AsyncSession, organization_id: int, active_only: bool = True,
) -> list[ScoreDecayRule]:
    q = select(ScoreDecayRule).where(ScoreDecayRule.organization_id == organization_id)
    if active_only:
        q = q.where(ScoreDecayRule.is_active.is_(True))
    result = await db.execute(q.order_by(ScoreDecayRule.id))
    return list(result.scalars().all())


async def update_rule(
    db: AsyncSession, rule_id: int, organization_id: int, **kwargs,
) -> ScoreDecayRule | None:
    result = await db.execute(
        select(ScoreDecayRule).where(
            ScoreDecayRule.id == rule_id,
            ScoreDecayRule.organization_id == organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(rule, k):
            setattr(rule, k, v)
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, rule_id: int, organization_id: int) -> bool:
    result = await db.execute(
        select(ScoreDecayRule).where(
            ScoreDecayRule.id == rule_id,
            ScoreDecayRule.organization_id == organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return False
    rule.is_active = False
    await db.commit()
    return True


async def simulate_decay(
    db: AsyncSession, rule_id: int, organization_id: int,
) -> dict:
    """Simulate what a decay run would do without applying changes."""
    result = await db.execute(
        select(ScoreDecayRule).where(
            ScoreDecayRule.id == rule_id,
            ScoreDecayRule.organization_id == organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return {"error": "Rule not found"}
    return {
        "rule_id": rule.id,
        "name": rule.name,
        "inactive_days": rule.inactive_days,
        "decay_points": rule.decay_points,
        "min_score": rule.min_score,
        "dry_run": True,
        "estimated_contacts": 0,
    }
