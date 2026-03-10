"""Contact deduplication rules service."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dedup_rule import DedupRule


async def create_rule(
    db: AsyncSession, *, organization_id: int, name: str,
    match_fields: list[str] | None = None,
    merge_strategy: str = "keep_newest",
    confidence_threshold: float = 0.8,
    auto_merge: bool = False, is_active: bool = True,
) -> DedupRule:
    row = DedupRule(
        organization_id=organization_id, name=name,
        match_fields=json.dumps(match_fields or []),
        merge_strategy=merge_strategy,
        confidence_threshold=confidence_threshold,
        auto_merge=auto_merge, is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_rules(
    db: AsyncSession, organization_id: int, *,
    is_active: bool | None = None,
) -> list[DedupRule]:
    q = select(DedupRule).where(DedupRule.organization_id == organization_id)
    if is_active is not None:
        q = q.where(DedupRule.is_active == is_active)
    q = q.order_by(DedupRule.name)
    return list((await db.execute(q)).scalars().all())


async def get_rule(db: AsyncSession, rule_id: int, organization_id: int) -> DedupRule | None:
    q = select(DedupRule).where(DedupRule.id == rule_id, DedupRule.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_rule(db: AsyncSession, rule_id: int, organization_id: int, **kwargs) -> DedupRule | None:
    row = await get_rule(db, rule_id, organization_id)
    if not row:
        return None
    if "match_fields" in kwargs:
        kwargs["match_fields"] = json.dumps(kwargs["match_fields"] or [])
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


async def check_duplicates(db: AsyncSession, organization_id: int, contact_data: dict) -> dict:
    rules = await list_rules(db, organization_id, is_active=True)
    matches = []
    for rule in rules:
        fields = json.loads(rule.match_fields)
        matched_fields = [f for f in fields if f in contact_data and contact_data[f]]
        if matched_fields:
            confidence = len(matched_fields) / len(fields) if fields else 0
            if confidence >= float(rule.confidence_threshold):
                matches.append({
                    "rule_id": rule.id, "rule_name": rule.name,
                    "matched_fields": matched_fields,
                    "confidence": round(confidence, 2),
                    "auto_merge": rule.auto_merge,
                })
    return {"potential_duplicates": matches}
