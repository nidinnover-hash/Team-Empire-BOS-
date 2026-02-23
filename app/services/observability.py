"""
Observability service — aggregate AI call metrics, approval stats, and decision traces.
"""

from datetime import datetime, timedelta, timezone
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_call_log import AiCallLog
from app.models.approval import Approval
from app.models.decision_trace import DecisionTrace


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


async def get_observability_summary(
    db: AsyncSession, org_id: int, days: int = 7
) -> ObservabilitySummary:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # AI call stats
    ai_result = await db.execute(
        select(
            AiCallLog.provider,
            func.count(AiCallLog.id).label("call_count"),
            func.avg(AiCallLog.latency_ms).label("avg_latency"),
            func.sum(AiCallLog.input_tokens).label("total_input_tokens"),
            func.sum(AiCallLog.output_tokens).label("total_output_tokens"),
        )
        .where(
            AiCallLog.organization_id == org_id,
            AiCallLog.created_at >= cutoff,
        )
        .group_by(AiCallLog.provider)
    )
    provider_stats: list[ProviderStats] = []
    total_calls = 0
    total_fallbacks = 0
    for row in ai_result.all():
        provider_stats.append({
            "provider": row.provider,
            "call_count": row.call_count,
            "avg_latency_ms": round(float(row.avg_latency or 0)),
            "total_input_tokens": int(row.total_input_tokens or 0),
            "total_output_tokens": int(row.total_output_tokens or 0),
        })
        total_calls += row.call_count

    # Fallback rate
    fb_result = await db.execute(
        select(func.count(AiCallLog.id))
        .where(
            AiCallLog.organization_id == org_id,
            AiCallLog.created_at >= cutoff,
            AiCallLog.used_fallback.is_(True),
        )
    )
    total_fallbacks = fb_result.scalar() or 0

    # Error rate
    err_result = await db.execute(
        select(func.count(AiCallLog.id))
        .where(
            AiCallLog.organization_id == org_id,
            AiCallLog.created_at >= cutoff,
            AiCallLog.error_type.isnot(None),
        )
    )
    total_errors = err_result.scalar() or 0

    # Approval stats
    approval_result = await db.execute(
        select(Approval.status, func.count(Approval.id))
        .where(Approval.organization_id == org_id, Approval.created_at >= cutoff)
        .group_by(Approval.status)
    )
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
    }


async def get_recent_ai_calls(
    db: AsyncSession, org_id: int, limit: int = 50
) -> list[RecentAiCall]:
    result = await db.execute(
        select(AiCallLog)
        .where(AiCallLog.organization_id == org_id)
        .order_by(AiCallLog.created_at.desc())
        .limit(limit)
    )
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
    result = await db.execute(
        select(DecisionTrace)
        .where(DecisionTrace.organization_id == org_id)
        .order_by(DecisionTrace.created_at.desc())
        .limit(limit)
    )
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
