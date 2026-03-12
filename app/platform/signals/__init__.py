"""Unified signal and event backbone for the modular monolith."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.signals.models import SignalCategory, SignalEnvelope
from app.platform.signals.publisher import InProcessSignalPublisher, SignalPublisher
from app.platform.signals.runtime import (
    get_persistent_signal_store,
    get_signal_publisher,
    get_signal_store,
)
from app.platform.signals.store import InMemorySignalStore, SignalStore, SqlAlchemySignalStore
from app.platform.signals.topics import (
    AI_CALL_COMPLETED,
    AI_CALL_FAILED,
    ANOMALY_DETECTED,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
    APPROVAL_REQUESTED,
    CONTACT_CREATED,
    CONTACT_DELETED,
    CONTACT_ROUTED,
    CONTACT_UPDATED,
    EXECUTION_COMPLETED,
    EXECUTION_FAILED,
    EXECUTION_STARTED,
    FINANCE_EXPENSE_RECORDED,
    FINANCE_INVOICE_CREATED,
    FINANCE_PAYMENT_RECEIVED,
    INTEGRATION_CONNECTED,
    INTEGRATION_DISCONNECTED,
    INTEGRATION_SYNC_COMPLETED,
    INTEGRATION_SYNC_FAILED,
    KNOWLEDGE_SAVE_FAILED,
    LEAD_CREATED_FROM_SOCIAL,
    MEMORY_UPDATED,
    PLAYBOOK_CREATED,
    PLAYBOOK_STEP_EXECUTED,
    PLAYBOOK_UPDATED,
    QUOTE_CREATED,
    QUOTE_LINE_ITEM_ADDED,
    QUOTE_LINE_ITEM_REMOVED,
    QUOTE_UPDATED,
    SCHEDULER_JOB_COMPLETED,
    SCHEDULER_JOB_FAILED,
    SLO_BREACH_DETECTED,
    SURVEY_DEFINITION_CREATED,
    SURVEY_RESPONSE_SUBMITTED,
    USER_LOGIN,
    USER_LOGOUT,
    WEBHOOK_DELIVERY_FAILED,
    WEBHOOK_DELIVERY_SUCCEEDED,
    WORKFLOW_DEFINITION_CREATED,
    WORKFLOW_DEFINITION_PUBLISHED,
    WORKFLOW_DEFINITION_UPDATED,
    WORKFLOW_PLAN_GENERATED,
    WORKFLOW_RUN_AWAITING_APPROVAL,
    WORKFLOW_RUN_COMPLETED,
    WORKFLOW_RUN_CREATED,
    WORKFLOW_RUN_FAILED,
    WORKFLOW_RUN_STARTED,
    WORKFLOW_STEP_BLOCKED,
    WORKFLOW_STEP_COMPLETED,
    WORKFLOW_STEP_FAILED,
    WORKFLOW_STEP_STARTED,
)


async def publish_signal(signal: SignalEnvelope, *, db: AsyncSession | None = None) -> SignalEnvelope:
    """Official write path for BOS signals.

    When SIGNAL_SYSTEM_ENABLED is False, signals are silently dropped.
    When db is provided, the signal is persisted to the signals table.
    """
    from app.core.config import settings

    if not settings.SIGNAL_SYSTEM_ENABLED:
        return signal
    if db is not None:
        await get_persistent_signal_store().append(signal, db=db)
    return await get_signal_publisher().publish(signal)

__all__ = [
    "AI_CALL_COMPLETED",
    "AI_CALL_FAILED",
    "ANOMALY_DETECTED",
    "APPROVAL_APPROVED",
    "APPROVAL_REJECTED",
    "APPROVAL_REQUESTED",
    "CONTACT_CREATED",
    "CONTACT_DELETED",
    "CONTACT_ROUTED",
    "CONTACT_UPDATED",
    "EXECUTION_COMPLETED",
    "EXECUTION_FAILED",
    "EXECUTION_STARTED",
    "FINANCE_EXPENSE_RECORDED",
    "FINANCE_INVOICE_CREATED",
    "FINANCE_PAYMENT_RECEIVED",
    "INTEGRATION_CONNECTED",
    "INTEGRATION_DISCONNECTED",
    "INTEGRATION_SYNC_COMPLETED",
    "INTEGRATION_SYNC_FAILED",
    "KNOWLEDGE_SAVE_FAILED",
    "LEAD_CREATED_FROM_SOCIAL",
    "MEMORY_UPDATED",
    "PLAYBOOK_CREATED",
    "PLAYBOOK_STEP_EXECUTED",
    "PLAYBOOK_UPDATED",
    "QUOTE_CREATED",
    "QUOTE_LINE_ITEM_ADDED",
    "QUOTE_LINE_ITEM_REMOVED",
    "QUOTE_UPDATED",
    "SCHEDULER_JOB_COMPLETED",
    "SCHEDULER_JOB_FAILED",
    "SLO_BREACH_DETECTED",
    "SURVEY_DEFINITION_CREATED",
    "SURVEY_RESPONSE_SUBMITTED",
    "USER_LOGIN",
    "USER_LOGOUT",
    "WEBHOOK_DELIVERY_FAILED",
    "WEBHOOK_DELIVERY_SUCCEEDED",
    "WORKFLOW_DEFINITION_CREATED",
    "WORKFLOW_DEFINITION_PUBLISHED",
    "WORKFLOW_DEFINITION_UPDATED",
    "WORKFLOW_PLAN_GENERATED",
    "WORKFLOW_RUN_AWAITING_APPROVAL",
    "WORKFLOW_RUN_COMPLETED",
    "WORKFLOW_RUN_CREATED",
    "WORKFLOW_RUN_FAILED",
    "WORKFLOW_RUN_STARTED",
    "WORKFLOW_STEP_BLOCKED",
    "WORKFLOW_STEP_COMPLETED",
    "WORKFLOW_STEP_FAILED",
    "WORKFLOW_STEP_STARTED",
    "InMemorySignalStore",
    "InProcessSignalPublisher",
    "SignalCategory",
    "SignalEnvelope",
    "SignalPublisher",
    "SignalStore",
    "SqlAlchemySignalStore",
    "get_persistent_signal_store",
    "get_signal_publisher",
    "get_signal_store",
    "publish_signal",
]
