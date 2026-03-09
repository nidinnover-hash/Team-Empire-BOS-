"""Deal risk scoring service."""
from __future__ import annotations

import json

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal_risk import DealRiskScore

RISK_LEVELS = ["low", "medium", "high", "critical"]


def _compute_risk_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


async def score_deal(
    db: AsyncSession, *, organization_id: int, deal_id: int,
    risk_score: int, factors: list[str] | None = None,
) -> DealRiskScore:
    risk_level = _compute_risk_level(risk_score)
    factors_json = json.dumps(factors or [])
    # Upsert: update if existing score for this deal
    q = select(DealRiskScore).where(
        DealRiskScore.organization_id == organization_id,
        DealRiskScore.deal_id == deal_id,
    )
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing:
        existing.risk_score = risk_score
        existing.risk_level = risk_level
        existing.factors_json = factors_json
        await db.commit()
        await db.refresh(existing)
        return existing
    row = DealRiskScore(
        organization_id=organization_id, deal_id=deal_id,
        risk_score=risk_score, risk_level=risk_level,
        factors_json=factors_json,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_deal_risk(db: AsyncSession, deal_id: int, organization_id: int) -> DealRiskScore | None:
    q = select(DealRiskScore).where(
        DealRiskScore.deal_id == deal_id,
        DealRiskScore.organization_id == organization_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def list_risks(
    db: AsyncSession, organization_id: int, *, risk_level: str | None = None, limit: int = 50,
) -> list[DealRiskScore]:
    q = select(DealRiskScore).where(DealRiskScore.organization_id == organization_id)
    if risk_level:
        q = q.where(DealRiskScore.risk_level == risk_level)
    q = q.order_by(DealRiskScore.risk_score.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_risk_summary(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(DealRiskScore.risk_level, func.count(DealRiskScore.id))
        .where(DealRiskScore.organization_id == organization_id)
        .group_by(DealRiskScore.risk_level)
    )).all()
    summary = {level: 0 for level in RISK_LEVELS}
    for level, count in rows:
        summary[level] = count
    return summary
