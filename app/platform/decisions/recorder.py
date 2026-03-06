"""Decision recording — persist + signal in one call."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.decisions.envelope import DecisionEnvelope, DecisionOutcome
from app.platform.signals import SignalCategory, SignalEnvelope, publish_signal

logger = logging.getLogger(__name__)

DECISION_SIGNAL_TOPIC = "decision.recorded"


async def record_decision(
    db: AsyncSession,
    *,
    decision_type: str,
    outcome: DecisionOutcome,
    confidence: float,
    organization_id: int,
    reasoning: str = "",
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    signal_ids: list[str] | None = None,
    metadata: dict[str, object] | None = None,
    request_id: str | None = None,
    daily_run_id: int | None = None,
) -> DecisionEnvelope:
    """Record a decision to the DB and emit a signal.

    Returns a ``DecisionEnvelope`` the caller can use to branch on outcome.
    """
    from app.models.decision_trace import DecisionTrace

    trace = DecisionTrace(
        organization_id=organization_id,
        trace_type=decision_type,
        title=f"{decision_type}:{outcome.value}",
        summary=reasoning or f"Auto-decision: {decision_type} -> {outcome.value}",
        confidence_score=confidence,
        signals_json={"signal_ids": signal_ids or [], **(metadata or {})},
        actor_user_id=actor_user_id,
        request_id=request_id,
        daily_run_id=daily_run_id,
    )
    db.add(trace)
    await db.flush()
    await db.refresh(trace)

    envelope = DecisionEnvelope(
        decision_type=decision_type,
        outcome=outcome,
        confidence=confidence,
        reasoning=reasoning,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        signal_ids=signal_ids or [],
        metadata=metadata or {},
        trace_id=trace.id,
    )

    try:
        await publish_signal(
            SignalEnvelope(
                topic=DECISION_SIGNAL_TOPIC,
                category=SignalCategory.DECISION,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                source="platform.decisions",
                entity_type=entity_type or "decision",
                entity_id=str(trace.id),
                correlation_id=request_id,
                summary_text=f"{decision_type}:{outcome.value} (conf={confidence:.2f})",
                payload={
                    "decision_id": envelope.decision_id,
                    "decision_type": decision_type,
                    "outcome": outcome.value,
                    "confidence": confidence,
                    "trace_id": trace.id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                },
            ),
            db=db,
        )
    except Exception:
        logger.debug("Failed to emit decision signal for trace=%d", trace.id, exc_info=True)

    return envelope
