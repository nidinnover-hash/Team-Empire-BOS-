"""
Observability service — aggregate AI call metrics, approval stats, and decision traces.
"""

from datetime import UTC, datetime, timedelta
from typing import TypedDict

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.idempotency import get_idempotency_stats
from app.core.middleware import get_rate_limit_stats
from app.core.resilience import get_retry_stats
from app.core.tenant import apply_org_scope
from app.engines.intelligence import projections as signal_projections
from app.engines.intelligence.projections import (
    AiReliability,
    DecisionSummary,
    DecisionTimelineItem,
    SchedulerHealth,
    WebhookReliability,
)
from app.models.ai_call_log import AiCallLog
from app.models.approval import Approval
from app.models.chat_message import ChatMessage
from app.models.decision_trace import DecisionTrace
from app.models.goal import Goal
from app.models.integration import Integration
from app.models.memory import DailyContext, ProfileMemory
from app.models.note import Note
from app.models.project import Project
from app.models.signal import Signal
from app.models.task import Task
from app.platform.signals.query import (
    list_recent_signals_by_org,
    list_recent_signals_by_topic,
    list_signals_by_correlation,
    list_signals_by_entity,
)
from app.services.signal_ingestion import get_ingestion_stats


class ProviderStats(TypedDict):
    provider: str
    call_count: int
    avg_latency_ms: int
    total_input_tokens: int
    total_output_tokens: int


class ObservabilitySummary(TypedDict):
    days: int
    total_ai_calls: int
    provider_stats: list[ProviderStats]
    fallback_rate: float
    error_rate: float
    total_approvals: int
    rejection_rate: float
    approval_breakdown: dict[str, int]
    runtime_stats: dict[str, int]


class RecentAiCall(TypedDict):
    id: int
    provider: str
    model_name: str | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    used_fallback: bool
    fallback_from: str | None
    error_type: str | None
    request_id: str | None
    created_at: str | None


class RecentDecision(TypedDict):
    id: int
    trace_type: str
    title: str
    summary: str
    confidence_score: float
    request_id: str | None
    created_at: str | None


class StorageTableStat(TypedDict):
    table: str
    row_count: int


class StorageSummary(TypedDict):
    org_id: int
    generated_at: datetime
    total_rows: int
    retention_days_chat: int
    tables: list[StorageTableStat]


class RecentSignal(TypedDict):
    id: int
    signal_id: str
    organization_id: int
    workspace_id: int | None
    actor_user_id: int | None
    topic: str
    category: str
    source: str
    entity_type: str | None
    entity_id: str | None
    correlation_id: str | None
    causation_id: str | None
    request_id: str | None
    summary_text: str | None
    payload: dict
    metadata: dict
    occurred_at: str | None
    created_at: str | None


def _serialize_signal(row: Signal) -> RecentSignal:
    return {
        "id": row.id,
        "signal_id": row.signal_id,
        "organization_id": row.organization_id,
        "workspace_id": row.workspace_id,
        "actor_user_id": row.actor_user_id,
        "topic": row.topic,
        "category": row.category,
        "source": row.source,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "correlation_id": row.correlation_id,
        "causation_id": row.causation_id,
        "request_id": row.request_id,
        "summary_text": row.summary_text,
        "payload": row.payload_json if isinstance(row.payload_json, dict) else {},
        "metadata": row.metadata_json if isinstance(row.metadata_json, dict) else {},
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def get_observability_summary(
    db: AsyncSession, org_id: int, days: int = 7
) -> ObservabilitySummary:
    cutoff = datetime.now(UTC) - timedelta(days=days)

    # AI call stats + fallback/error counts in a single query (was 3 separate queries)
    ai_query = select(
        AiCallLog.provider,
        func.count(AiCallLog.id).label("call_count"),
        func.avg(AiCallLog.latency_ms).label("avg_latency"),
        func.sum(AiCallLog.input_tokens).label("total_input_tokens"),
        func.sum(AiCallLog.output_tokens).label("total_output_tokens"),
        func.sum(func.cast(AiCallLog.used_fallback, Integer)).label("fallback_count"),
        func.count(AiCallLog.error_type).label("error_count"),
    )
    ai_query = apply_org_scope(ai_query, AiCallLog, org_id).where(AiCallLog.created_at >= cutoff)
    ai_result = await db.execute(ai_query.group_by(AiCallLog.provider))
    provider_stats: list[ProviderStats] = []
    total_calls = 0
    total_fallbacks = 0
    total_errors = 0
    for row in ai_result.all():
        provider_stats.append({
            "provider": row.provider,
            "call_count": row.call_count,
            "avg_latency_ms": round(float(row.avg_latency or 0)),
            "total_input_tokens": int(row.total_input_tokens or 0),
            "total_output_tokens": int(row.total_output_tokens or 0),
        })
        total_calls += row.call_count
        total_fallbacks += int(row.fallback_count or 0)
        total_errors += int(row.error_count or 0)

    # Approval stats
    approval_query = select(Approval.status, func.count(Approval.id))
    approval_query = apply_org_scope(approval_query, Approval, org_id).where(Approval.created_at >= cutoff)
    approval_result = await db.execute(approval_query.group_by(Approval.status))
    approval_counts = {row[0]: row[1] for row in approval_result.all()}
    total_approvals = sum(approval_counts.values())
    rejected = approval_counts.get("rejected", 0)

    return {
        "days": days,
        "total_ai_calls": total_calls,
        "provider_stats": provider_stats,
        "fallback_rate": round(total_fallbacks / total_calls * 100, 1) if total_calls else 0,
        "error_rate": round(total_errors / total_calls * 100, 1) if total_calls else 0,
        "total_approvals": total_approvals,
        "rejection_rate": round(rejected / total_approvals * 100, 1) if total_approvals else 0,
        "approval_breakdown": approval_counts,
        "runtime_stats": {
            **{f"rate_limit_{k}": v for k, v in get_rate_limit_stats().items()},
            **{f"idempotency_{k}": v for k, v in get_idempotency_stats().items()},
            **{f"retry_{k}": v for k, v in get_retry_stats().items()},
            **{f"ingestion_{k}": v for k, v in get_ingestion_stats().items()},
        },
    }


async def get_recent_ai_calls(
    db: AsyncSession, org_id: int, limit: int = 50
) -> list[RecentAiCall]:
    ai_calls_query = select(AiCallLog)
    ai_calls_query = apply_org_scope(ai_calls_query, AiCallLog, org_id)
    result = await db.execute(ai_calls_query.order_by(AiCallLog.created_at.desc()).limit(limit))
    return [
        {
            "id": row.id,
            "provider": row.provider,
            "model_name": row.model_name,
            "latency_ms": row.latency_ms,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "used_fallback": row.used_fallback,
            "fallback_from": row.fallback_from,
            "error_type": row.error_type,
            "request_id": row.request_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in result.scalars().all()
    ]


async def get_recent_decisions(
    db: AsyncSession, org_id: int, limit: int = 20
) -> list[RecentDecision]:
    traces_query = select(DecisionTrace)
    traces_query = apply_org_scope(traces_query, DecisionTrace, org_id)
    result = await db.execute(traces_query.order_by(DecisionTrace.created_at.desc()).limit(limit))
    return [
        {
            "id": row.id,
            "trace_type": row.trace_type,
            "title": row.title,
            "summary": row.summary,
            "confidence_score": row.confidence_score,
            "request_id": row.request_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in result.scalars().all()
    ]


async def get_storage_summary(db: AsyncSession, org_id: int) -> StorageSummary:
    table_models = [
        ("tasks", Task),
        ("projects", Project),
        ("notes", Note),
        ("goals", Goal),
        ("integrations", Integration),
        ("profile_memory", ProfileMemory),
        ("daily_context", DailyContext),
        ("chat_messages", ChatMessage),
        ("ai_call_logs", AiCallLog),
        ("signals", Signal),
    ]

    stats: list[StorageTableStat] = []
    total_rows = 0

    for table_name, model in table_models:
        q = select(func.count()).select_from(model)
        q = apply_org_scope(q, model, org_id)
        result = await db.execute(q)
        count = int(result.scalar() or 0)
        total_rows += count
        stats.append({"table": table_name, "row_count": count})

    return {
        "org_id": org_id,
        "generated_at": datetime.now(UTC),
        "total_rows": total_rows,
        "retention_days_chat": int(settings.CHAT_HISTORY_RETENTION_DAYS),
        "tables": stats,
    }


async def get_recent_signals(
    db: AsyncSession,
    *,
    org_id: int,
    limit: int = 100,
    topic: str | None = None,
    correlation_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> list[RecentSignal]:
    if correlation_id:
        rows = await list_signals_by_correlation(
            db,
            organization_id=org_id,
            correlation_id=correlation_id,
            limit=limit,
        )
    elif entity_type and entity_id:
        rows = await list_signals_by_entity(
            db,
            organization_id=org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )
    elif topic:
        rows = await list_recent_signals_by_topic(
            db,
            organization_id=org_id,
            topic=topic,
            limit=limit,
        )
    else:
        rows = await list_recent_signals_by_org(
            db,
            organization_id=org_id,
            limit=limit,
        )
    return [_serialize_signal(row) for row in rows]


async def get_decision_timeline(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 50,
    correlation_id: str | None = None,
    approval_id: int | None = None,
) -> list[DecisionTimelineItem]:
    return await signal_projections.get_decision_timeline(
        db,
        org_id=org_id,
        days=days,
        limit=limit,
        correlation_id=correlation_id,
        approval_id=approval_id,
    )


async def get_decision_summary(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 200,
    correlation_id: str | None = None,
    approval_id: int | None = None,
) -> DecisionSummary:
    return await signal_projections.get_decision_summary(
        db,
        org_id=org_id,
        days=days,
        limit=limit,
        correlation_id=correlation_id,
        approval_id=approval_id,
    )


async def get_ai_reliability(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 200,
) -> AiReliability:
    return await signal_projections.get_ai_reliability(
        db,
        org_id=org_id,
        days=days,
        limit=limit,
    )


async def get_scheduler_health(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 300,
) -> SchedulerHealth:
    return await signal_projections.get_scheduler_health(
        db,
        org_id=org_id,
        days=days,
        limit=limit,
    )


async def get_webhook_reliability(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 300,
) -> WebhookReliability:
    return await signal_projections.get_webhook_reliability(
        db,
        org_id=org_id,
        days=days,
        limit=limit,
    )
