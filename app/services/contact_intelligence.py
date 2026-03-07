"""Contact Intelligence — AI-powered lead scoring, stale detection, and follow-up suggestions."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact

logger = logging.getLogger(__name__)


async def score_contact(contact: Contact) -> int:
    """Calculate a lead score (0-100) based on contact attributes and activity.

    Scoring rules:
    - Pipeline stage progression: new=5, contacted=15, qualified=30, proposal=50, negotiation=70, won=90, lost=0
    - Has deal value: +10
    - Has email: +5
    - Has phone: +5
    - Recently contacted (last 7 days): +10
    - Has follow-up scheduled: +5
    - Qualified status: qualified=+10, disqualified=-20
    """
    score = 0

    # Pipeline stage score
    stage_scores = {
        "new": 5, "contacted": 15, "qualified": 30,
        "proposal": 50, "negotiation": 70, "won": 90, "lost": 0,
    }
    score += stage_scores.get(contact.pipeline_stage, 5)

    # Contact completeness
    if contact.email:
        score += 5
    if contact.phone:
        score += 5
    if contact.deal_value and contact.deal_value > 0:
        score += 10

    # Activity recency
    now = datetime.now(UTC)
    if contact.last_contacted_at and (now - contact.last_contacted_at).days <= 7:
        score += 10

    # Follow-up scheduled
    if contact.next_follow_up_at:
        score += 5

    # Qualification status
    if contact.qualified_status == "qualified":
        score += 10
    elif contact.qualified_status == "disqualified":
        score -= 20

    return max(0, min(100, score))


async def batch_score_contacts(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 200,
) -> dict:
    """Re-score all contacts for an org and update lead_score. Returns count updated."""
    rows = (
        await db.execute(
            select(Contact)
            .where(Contact.organization_id == organization_id)
            .limit(limit)
        )
    ).scalars().all()

    updated = 0
    for contact in rows:
        new_score = await score_contact(contact)
        if contact.lead_score != new_score:
            contact.lead_score = new_score
            updated += 1

    if updated:
        await db.commit()

    return {"total_scored": len(rows), "updated": updated}


async def get_stale_contacts(
    db: AsyncSession,
    organization_id: int,
    *,
    stale_days: int = 30,
    limit: int = 50,
) -> list[dict]:
    """Contacts with no activity for stale_days and not in terminal stages (won/lost)."""
    cutoff = datetime.now(UTC) - timedelta(days=stale_days)

    query = (
        select(Contact)
        .where(
            Contact.organization_id == organization_id,
            Contact.pipeline_stage.notin_(["won", "lost"]),
        )
        .order_by(Contact.last_contacted_at.asc().nullsfirst())
        .limit(limit)
    )

    rows = (await db.execute(query)).scalars().all()

    now = datetime.now(UTC)
    stale = []
    for c in rows:
        # Stale if last_contacted_at is before cutoff or never contacted
        if c.last_contacted_at is None or c.last_contacted_at < cutoff:
            days_inactive = (
                (now - c.last_contacted_at).days if c.last_contacted_at else None
            )
            stale.append({
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "company": c.company,
                "pipeline_stage": c.pipeline_stage,
                "lead_score": c.lead_score,
                "days_inactive": days_inactive,
                "last_contacted_at": c.last_contacted_at.isoformat() if c.last_contacted_at else None,
                "deal_value": c.deal_value,
            })

    return stale


async def get_follow_up_suggestions(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 20,
) -> list[dict]:
    """Suggest contacts that need follow-up: overdue follow-ups + high-score contacts with no upcoming follow-up."""
    now = datetime.now(UTC)

    # 1. Overdue follow-ups
    overdue_q = (
        select(Contact)
        .where(
            Contact.organization_id == organization_id,
            Contact.next_follow_up_at.isnot(None),
            Contact.next_follow_up_at <= now,
            Contact.pipeline_stage.notin_(["won", "lost"]),
        )
        .order_by(Contact.next_follow_up_at.asc())
        .limit(limit)
    )
    overdue = (await db.execute(overdue_q)).scalars().all()

    # 2. High-score contacts without follow-up scheduled
    remaining = max(0, limit - len(overdue))
    overdue_ids = {c.id for c in overdue}
    no_followup_q = (
        select(Contact)
        .where(
            Contact.organization_id == organization_id,
            Contact.next_follow_up_at.is_(None),
            Contact.lead_score >= 30,
            Contact.pipeline_stage.notin_(["won", "lost"]),
        )
        .order_by(Contact.lead_score.desc())
        .limit(remaining + len(overdue_ids))  # fetch extra in case of overlap
    )
    no_followup = (await db.execute(no_followup_q)).scalars().all()

    suggestions = []
    for c in overdue:
        days_overdue = (now - c.next_follow_up_at).days if c.next_follow_up_at else 0
        suggestions.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "company": c.company,
            "pipeline_stage": c.pipeline_stage,
            "lead_score": c.lead_score,
            "reason": "overdue_follow_up",
            "days_overdue": days_overdue,
            "next_follow_up_at": c.next_follow_up_at.isoformat() if c.next_follow_up_at else None,
            "deal_value": c.deal_value,
        })

    for c in no_followup:
        if c.id in overdue_ids:
            continue
        if len(suggestions) >= limit:
            break
        suggestions.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "company": c.company,
            "pipeline_stage": c.pipeline_stage,
            "lead_score": c.lead_score,
            "reason": "high_score_no_follow_up",
            "days_overdue": None,
            "next_follow_up_at": None,
            "deal_value": c.deal_value,
        })

    return suggestions


async def get_pipeline_analytics(
    db: AsyncSession,
    organization_id: int,
) -> dict:
    """Pipeline stage distribution, conversion rates, and avg deal values."""
    rows = (
        await db.execute(
            select(
                Contact.pipeline_stage,
                func.count(Contact.id).label("count"),
                func.sum(Contact.deal_value).label("total_value"),
                func.avg(Contact.lead_score).label("avg_score"),
            )
            .where(Contact.organization_id == organization_id)
            .group_by(Contact.pipeline_stage)
        )
    ).all()

    stages = []
    total_contacts = 0
    for r in rows:
        count = r.count or 0
        total_contacts += count
        stages.append({
            "stage": r.pipeline_stage,
            "count": count,
            "total_value": float(r.total_value) if r.total_value else 0.0,
            "avg_score": round(r.avg_score) if r.avg_score else 0,
        })

    return {
        "total_contacts": total_contacts,
        "stages": stages,
    }


async def get_contact_intelligence_summary(
    db: AsyncSession,
    organization_id: int,
    *,
    stale_days: int = 30,
) -> dict:
    """Full contact intelligence: pipeline analytics + stale + follow-up suggestions."""
    pipeline = await get_pipeline_analytics(db, organization_id)
    stale = await get_stale_contacts(db, organization_id, stale_days=stale_days)
    suggestions = await get_follow_up_suggestions(db, organization_id)

    return {
        "pipeline": pipeline,
        "stale_contacts": stale,
        "follow_up_suggestions": suggestions,
        "stale_count": len(stale),
        "follow_up_count": len(suggestions),
    }
