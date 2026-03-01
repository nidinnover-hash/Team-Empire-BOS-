"""Sales clone coach — learns from lost leads, builds objection playbooks, trains clones."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales_interaction import SalesInteractionLog

logger = logging.getLogger(__name__)


async def record_interaction(
    db: AsyncSession,
    org_id: int,
    employee_id: int,
    interaction_type: str,
    *,
    contact_id: int | None = None,
    channel: str | None = None,
    objection_encountered: str | None = None,
    response_given: str | None = None,
    context_notes: str | None = None,
    outcome: str = "pending",
    outcome_score: float = 0.5,
    loss_reason: str | None = None,
) -> SalesInteractionLog:
    """Record a sales interaction touchpoint."""
    entry = SalesInteractionLog(
        organization_id=org_id,
        employee_id=employee_id,
        contact_id=contact_id,
        interaction_type=interaction_type,
        channel=channel,
        objection_encountered=objection_encountered,
        response_given=response_given,
        context_notes=context_notes,
        outcome=outcome,
        outcome_score=outcome_score,
        loss_reason=loss_reason,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_loss_patterns(
    db: AsyncSession,
    org_id: int,
    employee_id: int | None = None,
    days: int = 90,
) -> dict:
    """Analyze patterns in lost leads — objections, timing, channels."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    query = select(SalesInteractionLog).where(
        SalesInteractionLog.organization_id == org_id,
        SalesInteractionLog.outcome == "lost",
        SalesInteractionLog.created_at >= cutoff,
    )
    if employee_id:
        query = query.where(SalesInteractionLog.employee_id == employee_id)
    result = await db.execute(query.limit(500))
    lost = list(result.scalars().all())

    # Aggregate objection frequencies
    objection_freq: dict[str, int] = {}
    loss_reasons: dict[str, int] = {}
    channel_losses: dict[str, int] = {}
    for entry in lost:
        if entry.objection_encountered:
            obj_key = entry.objection_encountered.strip().lower()[:80]
            objection_freq[obj_key] = objection_freq.get(obj_key, 0) + 1
        if entry.loss_reason:
            lr = entry.loss_reason.strip().lower()[:60]
            loss_reasons[lr] = loss_reasons.get(lr, 0) + 1
        ch = entry.channel or entry.interaction_type
        channel_losses[ch] = channel_losses.get(ch, 0) + 1

    top_objections = sorted(objection_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    top_loss_reasons = sorted(loss_reasons.items(), key=lambda x: x[1], reverse=True)[:10]
    top_channel_losses = sorted(channel_losses.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "window_days": days,
        "total_lost": len(lost),
        "top_objections": [{"objection": k, "count": v} for k, v in top_objections],
        "top_loss_reasons": [{"reason": k, "count": v} for k, v in top_loss_reasons],
        "channel_losses": [{"channel": k, "count": v} for k, v in top_channel_losses],
        "avg_outcome_score": round(
            sum(e.outcome_score for e in lost) / len(lost) if lost else 0.0, 3,
        ),
    }


async def get_win_patterns(
    db: AsyncSession,
    org_id: int,
    employee_id: int | None = None,
    days: int = 90,
) -> dict:
    """Analyze patterns in successful conversions."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    query = select(SalesInteractionLog).where(
        SalesInteractionLog.organization_id == org_id,
        SalesInteractionLog.outcome == "converted",
        SalesInteractionLog.created_at >= cutoff,
    )
    if employee_id:
        query = query.where(SalesInteractionLog.employee_id == employee_id)
    result = await db.execute(query.limit(500))
    won = list(result.scalars().all())

    response_patterns: dict[str, int] = {}
    for entry in won:
        if entry.response_given:
            resp = entry.response_given.strip().lower()[:80]
            response_patterns[resp] = response_patterns.get(resp, 0) + 1

    top_responses = sorted(response_patterns.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "window_days": days,
        "total_won": len(won),
        "top_successful_responses": [{"response": k, "count": v} for k, v in top_responses],
        "avg_outcome_score": round(
            sum(e.outcome_score for e in won) / len(won) if won else 0.0, 3,
        ),
    }


async def generate_objection_playbook(
    db: AsyncSession,
    org_id: int,
    employee_id: int | None = None,
    days: int = 90,
) -> dict:
    """Generate an AI-powered objection handling playbook from interaction history."""
    losses = await get_loss_patterns(db, org_id, employee_id, days)
    wins = await get_win_patterns(db, org_id, employee_id, days)

    if losses["total_lost"] == 0 and wins["total_won"] == 0:
        return {
            "playbook": [],
            "summary": "No sales interactions recorded yet. Start logging interactions to build playbook.",
            "conversion_rate": 0.0,
        }

    total = losses["total_lost"] + wins["total_won"]
    conversion_rate = round(wins["total_won"] / total if total > 0 else 0.0, 3)

    # Build playbook entries from top objections matched with winning responses
    playbook: list[dict] = []
    for obj in losses["top_objections"][:5]:
        best_response = None
        if wins["top_successful_responses"]:
            best_response = wins["top_successful_responses"][0]["response"]
        playbook.append({
            "objection": obj["objection"],
            "frequency": obj["count"],
            "suggested_response": best_response or "No winning response pattern found yet — try a new approach and log it.",
            "source": "data_driven",
        })

    # AI-powered playbook generation (if available)
    if playbook:
        try:
            from app.services.ai_router import call_ai

            prompt_data = (
                f"Top objections: {[p['objection'] for p in playbook]}\n"
                f"Top winning responses: {[r['response'] for r in wins['top_successful_responses'][:5]]}\n"
                f"Conversion rate: {conversion_rate}\n"
                "Generate 3 specific objection-handling scripts."
            )
            ai_result = await call_ai(
                system_prompt=(
                    "You are a sales coaching AI. Analyze the objection patterns and winning "
                    "responses. Generate concise, actionable scripts. Output only the scripts, "
                    "each starting with 'OBJECTION:' then 'RESPONSE:'. Max 3 scripts."
                ),
                user_message=prompt_data,
                provider="groq",
                max_tokens=600,
            )
            playbook.append({"ai_scripts": ai_result, "source": "ai_generated"})
        except Exception:
            logger.debug("AI playbook generation skipped", exc_info=True)

    return {
        "playbook": playbook,
        "summary": f"{wins['total_won']} wins, {losses['total_lost']} losses in {days}d. Rate: {conversion_rate}",
        "conversion_rate": conversion_rate,
        "loss_patterns": losses,
        "win_patterns": wins,
    }


async def get_employee_sales_stats(
    db: AsyncSession,
    org_id: int,
    employee_id: int,
    days: int = 30,
) -> dict:
    """Get sales performance stats for a specific employee clone."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(
            SalesInteractionLog.outcome,
            func.count(SalesInteractionLog.id),
        ).where(
            SalesInteractionLog.organization_id == org_id,
            SalesInteractionLog.employee_id == employee_id,
            SalesInteractionLog.created_at >= cutoff,
        ).group_by(SalesInteractionLog.outcome)
    )
    counts = {row[0]: row[1] for row in result.all()}
    total = sum(counts.values())
    converted = counts.get("converted", 0)
    lost = counts.get("lost", 0)

    return {
        "employee_id": employee_id,
        "window_days": days,
        "total_interactions": total,
        "converted": converted,
        "lost": lost,
        "pending": counts.get("pending", 0),
        "deferred": counts.get("deferred", 0),
        "conversion_rate": round(converted / (converted + lost) if (converted + lost) > 0 else 0.0, 3),
    }


async def list_interactions(
    db: AsyncSession,
    org_id: int,
    employee_id: int | None = None,
    outcome: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[SalesInteractionLog]:
    """List sales interactions with optional filters."""
    query = select(SalesInteractionLog).where(
        SalesInteractionLog.organization_id == org_id,
    )
    if employee_id:
        query = query.where(SalesInteractionLog.employee_id == employee_id)
    if outcome:
        query = query.where(SalesInteractionLog.outcome == outcome)
    query = query.order_by(SalesInteractionLog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
