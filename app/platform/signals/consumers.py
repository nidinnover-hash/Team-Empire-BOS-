"""Signal consumers that react to published signals.

Consumers are registered once at startup via ``register_default_consumers()``.
Each consumer receives a ``SignalEnvelope`` and performs best-effort work;
failures are logged but never propagate to the publisher.
"""

import logging

from app.platform.signals.schemas import SignalEnvelope

logger = logging.getLogger(__name__)

_registered = False


async def _audit_log_consumer(signal: SignalEnvelope) -> None:
    """Bridge signals into the audit event log for compliance visibility."""
    from app.db.session import AsyncSessionLocal
    from app.models.event import Event

    try:
        async with AsyncSessionLocal() as db:
            db.add(
                Event(
                    organization_id=signal.organization_id,
                    actor_user_id=signal.actor_user_id,
                    event_type=f"signal.{signal.topic}",
                    payload_json={
                        "signal_id": signal.signal_id,
                        "source": signal.source,
                        "entity_type": signal.entity_type,
                        "entity_id": signal.entity_id,
                        "category": signal.category.value,
                        "summary": signal.summary_text,
                    },
                )
            )
            await db.commit()
    except Exception:
        logger.debug("Audit log consumer failed for signal %s", signal.signal_id, exc_info=True)


async def _metrics_counter_consumer(signal: SignalEnvelope) -> None:
    """Lightweight in-process counter for signal volume monitoring."""
    _signal_counts[signal.topic] = _signal_counts.get(signal.topic, 0) + 1


_signal_counts: dict[str, int] = {}


def get_signal_counts() -> dict[str, int]:
    """Return a snapshot of signal topic counts since process start."""
    return dict(_signal_counts)


def register_default_consumers() -> None:
    """Wire up built-in consumers to the runtime publisher.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _registered
    if _registered:
        return
    _registered = True

    from app.core.config import settings

    if not settings.SIGNAL_SYSTEM_ENABLED:
        logger.info("Signal system disabled — skipping consumer registration")
        return

    from app.platform.signals.runtime import get_signal_publisher

    publisher = get_signal_publisher()
    publisher.subscribe_all(_audit_log_consumer)
    publisher.subscribe_all(_metrics_counter_consumer)

    logger.info("Signal consumers registered: audit_log, metrics_counter")
