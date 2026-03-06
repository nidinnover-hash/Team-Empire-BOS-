"""Decision abstraction layer for the BOS runtime.

Every AI-driven or rule-driven decision flows through ``record_decision()``,
which persists a ``DecisionTrace`` row, emits a signal, and returns a
typed ``DecisionEnvelope`` for the caller to act on.
"""

from app.platform.decisions.envelope import DecisionEnvelope, DecisionOutcome
from app.platform.decisions.recorder import record_decision
from app.platform.decisions.types import (
    DECISION_APPROVAL_AUTO,
    DECISION_CONTACT_ROUTE,
    DECISION_EMAIL_DRAFT,
    DECISION_ESCALATION,
    DECISION_LEAD_SCORE,
    DECISION_TASK_SUGGEST,
)

__all__ = [
    "DECISION_APPROVAL_AUTO",
    "DECISION_CONTACT_ROUTE",
    "DECISION_EMAIL_DRAFT",
    "DECISION_ESCALATION",
    "DECISION_LEAD_SCORE",
    "DECISION_TASK_SUGGEST",
    "DecisionEnvelope",
    "DecisionOutcome",
    "record_decision",
]
