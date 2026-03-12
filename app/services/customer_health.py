"""Customer health score service."""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_health import CustomerHealthScore


def _compute_risk(score: int) -> str:
    if score >= 80:
        return "healthy"
    if score >= 60:
        return "monitor"
    if score >= 40:
        return "at_risk"
    return "critical"


async def upsert_score(
    db: AsyncSession, *, organization_id: int, contact_id: int,
    usage_score: int = 0, engagement_score: int = 0,
    support_score: int = 0, payment_score: int = 0,
    factors: dict | None = None,
) -> CustomerHealthScore:
    q = select(CustomerHealthScore).where(
        CustomerHealthScore.organization_id == organization_id,
        CustomerHealthScore.contact_id == contact_id,
    )
    row = (await db.execute(q)).scalar_one_or_none()
    overall = (usage_score + engagement_score + support_score + payment_score) // 4
    if row:
        row.previous_score = row.overall_score
        row.usage_score = usage_score
        row.engagement_score = engagement_score
        row.support_score = support_score
        row.payment_score = payment_score
        row.overall_score = overall
        row.risk_level = _compute_risk(overall)
        row.factors_json = json.dumps(factors or {})
    else:
        row = CustomerHealthScore(
            organization_id=organization_id, contact_id=contact_id,
            usage_score=usage_score, engagement_score=engagement_score,
            support_score=support_score, payment_score=payment_score,
            overall_score=overall, risk_level=_compute_risk(overall),
            factors_json=json.dumps(factors or {}),
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_score(db: AsyncSession, contact_id: int, organization_id: int) -> CustomerHealthScore | None:
    q = select(CustomerHealthScore).where(
        CustomerHealthScore.organization_id == organization_id,
        CustomerHealthScore.contact_id == contact_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def list_scores(
    db: AsyncSession, organization_id: int, *,
    risk_level: str | None = None, limit: int = 100,
) -> list[CustomerHealthScore]:
    q = select(CustomerHealthScore).where(CustomerHealthScore.organization_id == organization_id)
    if risk_level:
        q = q.where(CustomerHealthScore.risk_level == risk_level)
    q = q.order_by(CustomerHealthScore.overall_score.asc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_summary(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(CustomerHealthScore.risk_level, func.count(CustomerHealthScore.id))
        .where(CustomerHealthScore.organization_id == organization_id)
        .group_by(CustomerHealthScore.risk_level)
    )).all()
    return {level: count for level, count in rows}
