"""Signal-derived intelligence projections for Observe and founder control surfaces."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.platform.signals.topics import (
    AI_CALL_COMPLETED,
    AI_CALL_FAILED,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
    APPROVAL_REQUESTED,
    EXECUTION_COMPLETED,
    EXECUTION_FAILED,
    EXECUTION_STARTED,
    SCHEDULER_JOB_COMPLETED,
    SCHEDULER_JOB_FAILED,
    WEBHOOK_DELIVERY_FAILED,
    WEBHOOK_DELIVERY_SUCCEEDED,
)


class DecisionTimelineEvent(TypedDict):
    topic: str
    occurred_at: str | None
    source: str
    summary_text: str | None
    payload: dict


class DecisionTimelineItem(TypedDict):
    approval_id: int
    approval_type: str | None
    approval_status: str | None
    execution_id: int | None
    execution_status: str | None
    requested_at: str | None
    decided_at: str | None
    execution_started_at: str | None
    execution_finished_at: str | None
    approval_to_execution_ms: int | None
    stalled: bool
    timeline: list[DecisionTimelineEvent]


class DecisionSummaryItem(TypedDict):
    approval_id: int
    approval_type: str | None
    approval_status: str | None
    execution_id: int | None
    execution_status: str | None
    requested_at: str | None
    decided_at: str | None
    execution_started_at: str | None
    execution_finished_at: str | None
    approval_to_execution_ms: int | None


class DecisionSummary(TypedDict):
    days: int
    total_requests: int
    approved_count: int
    rejected_count: int
    pending_count: int
    approved_but_not_executed_count: int
    execution_failed_count: int
    median_approval_to_execution_ms: int | None
    recent_stalled: list[DecisionSummaryItem]
    recent_failed: list[DecisionSummaryItem]


class AiReliabilityProvider(TypedDict):
    provider: str
    total_calls: int
    failed_calls: int
    fallback_count: int
    error_rate: float
    fallback_rate: float
    avg_latency_ms: int


class AiReliabilityFailure(TypedDict):
    signal_id: str
    provider: str | None
    model_name: str | None
    error_type: str | None
    request_id: str | None
    fallback_from: str | None
    latency_ms: int | None
    occurred_at: str | None


class AiReliability(TypedDict):
    days: int
    total_calls: int
    failed_calls: int
    fallback_count: int
    success_rate: float
    error_rate: float
    fallback_rate: float
    avg_latency_ms: int | None
    providers: list[AiReliabilityProvider]
    recent_failures: list[AiReliabilityFailure]


class SchedulerHealthJob(TypedDict):
    job_name: str
    total_runs: int
    failed_runs: int
    success_rate: float
    avg_duration_ms: int
    last_status: str | None
    last_occurred_at: str | None


class SchedulerHealthFailure(TypedDict):
    signal_id: str
    job_name: str
    error: str | None
    duration_ms: int | None
    occurred_at: str | None


class SchedulerHealth(TypedDict):
    days: int
    total_runs: int
    failed_runs: int
    success_rate: float
    avg_duration_ms: int | None
    jobs: list[SchedulerHealthJob]
    recent_failures: list[SchedulerHealthFailure]


class WebhookReliabilityEndpoint(TypedDict):
    endpoint_id: int | None
    total_deliveries: int
    failed_deliveries: int
    success_rate: float
    avg_duration_ms: int
    last_status: str | None
    last_event: str | None
    last_occurred_at: str | None


class WebhookReliabilityFailure(TypedDict):
    signal_id: str
    endpoint_id: int | None
    event: str | None
    error_message: str | None
    response_status_code: int | None
    duration_ms: int | None
    occurred_at: str | None


class WebhookReliability(TypedDict):
    days: int
    total_deliveries: int
    failed_deliveries: int
    success_rate: float
    avg_duration_ms: int | None
    endpoints: list[WebhookReliabilityEndpoint]
    recent_failures: list[WebhookReliabilityFailure]


async def get_decision_timeline(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 50,
    correlation_id: str | None = None,
    approval_id: int | None = None,
) -> list[DecisionTimelineItem]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    tracked_topics = [
        APPROVAL_REQUESTED,
        APPROVAL_APPROVED,
        APPROVAL_REJECTED,
        EXECUTION_STARTED,
        EXECUTION_COMPLETED,
        EXECUTION_FAILED,
    ]
    query = (
        select(Signal)
        .where(
            Signal.organization_id == org_id,
            Signal.topic.in_(tracked_topics),
            Signal.occurred_at >= cutoff,
        )
        .order_by(Signal.occurred_at.desc(), Signal.id.desc())
    )
    if correlation_id:
        query = query.where(Signal.correlation_id == correlation_id)
    result = await db.execute(query.limit(limit * 20))
    rows = list(result.scalars().all())
    grouped: dict[int, list[Signal]] = defaultdict(list)
    for row in rows:
        approval_id_raw = None
        if row.entity_type == "approval" and row.entity_id:
            approval_id_raw = row.entity_id
        elif isinstance(row.payload_json, dict):
            approval_id_raw = row.payload_json.get("approval_id")
        try:
            grouped_id = int(approval_id_raw)
        except (TypeError, ValueError):
            continue
        grouped[grouped_id].append(row)

    items: list[DecisionTimelineItem] = []
    for grouped_approval_id, signal_rows in grouped.items():
        if approval_id is not None and grouped_approval_id != approval_id:
            continue
        ordered = sorted(
            signal_rows,
            key=lambda row: ((row.occurred_at or datetime.min.replace(tzinfo=UTC)), row.id),
        )
        requested_at = None
        decided_at = None
        execution_started_at = None
        execution_finished_at = None
        approval_type = None
        approval_status = None
        execution_id = None
        execution_status = None
        timeline: list[DecisionTimelineEvent] = []

        for row in ordered:
            payload = row.payload_json if isinstance(row.payload_json, dict) else {}
            timeline.append(
                {
                    "topic": row.topic,
                    "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                    "source": row.source,
                    "summary_text": row.summary_text,
                    "payload": payload,
                }
            )
            if row.topic == APPROVAL_REQUESTED:
                requested_at = row.occurred_at
                approval_type = str(payload.get("approval_type") or approval_type or "")
                approval_status = str(payload.get("status") or "pending")
            elif row.topic in {APPROVAL_APPROVED, APPROVAL_REJECTED}:
                decided_at = row.occurred_at
                approval_type = str(payload.get("approval_type") or approval_type or "")
                approval_status = str(payload.get("status") or approval_status or "")
            elif row.topic == EXECUTION_STARTED:
                execution_started_at = row.occurred_at
                execution_id = int(payload.get("execution_id") or 0) or execution_id
                execution_status = str(payload.get("status") or "running")
            elif row.topic in {EXECUTION_COMPLETED, EXECUTION_FAILED}:
                execution_finished_at = row.occurred_at
                execution_id = int(payload.get("execution_id") or 0) or execution_id
                execution_status = str(payload.get("status") or execution_status or "")

        approval_to_execution_ms = None
        if decided_at and execution_started_at:
            approval_to_execution_ms = max(0, int((execution_started_at - decided_at).total_seconds() * 1000))
        stalled = bool(
            approval_status == "approved"
            and execution_started_at is None
            and decided_at is not None
        )
        items.append(
            {
                "approval_id": grouped_approval_id,
                "approval_type": approval_type or None,
                "approval_status": approval_status or None,
                "execution_id": execution_id,
                "execution_status": execution_status,
                "requested_at": requested_at.isoformat() if requested_at else None,
                "decided_at": decided_at.isoformat() if decided_at else None,
                "execution_started_at": execution_started_at.isoformat() if execution_started_at else None,
                "execution_finished_at": execution_finished_at.isoformat() if execution_finished_at else None,
                "approval_to_execution_ms": approval_to_execution_ms,
                "stalled": stalled,
                "timeline": timeline,
            }
        )

    items.sort(
        key=lambda item: item["requested_at"] or item["decided_at"] or item["execution_finished_at"] or "",
        reverse=True,
    )
    return items[:limit]


def _to_decision_summary_item(item: DecisionTimelineItem) -> DecisionSummaryItem:
    return {
        "approval_id": item["approval_id"],
        "approval_type": item["approval_type"],
        "approval_status": item["approval_status"],
        "execution_id": item["execution_id"],
        "execution_status": item["execution_status"],
        "requested_at": item["requested_at"],
        "decided_at": item["decided_at"],
        "execution_started_at": item["execution_started_at"],
        "execution_finished_at": item["execution_finished_at"],
        "approval_to_execution_ms": item["approval_to_execution_ms"],
    }


async def get_decision_summary(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 200,
    correlation_id: str | None = None,
    approval_id: int | None = None,
) -> DecisionSummary:
    timeline = await get_decision_timeline(
        db,
        org_id=org_id,
        days=days,
        limit=limit,
        correlation_id=correlation_id,
        approval_id=approval_id,
    )
    approved = [item for item in timeline if item["approval_status"] == "approved"]
    rejected = [item for item in timeline if item["approval_status"] == "rejected"]
    pending = [item for item in timeline if item["approval_status"] == "pending"]
    stalled = [item for item in timeline if item["stalled"]]
    failed = [item for item in timeline if item["execution_status"] == "failed"]
    latency_values = sorted(
        item["approval_to_execution_ms"]
        for item in timeline
        if item["approval_to_execution_ms"] is not None
    )
    median_latency = None
    if latency_values:
        mid = len(latency_values) // 2
        if len(latency_values) % 2 == 1:
            median_latency = int(latency_values[mid])
        else:
            median_latency = int((latency_values[mid - 1] + latency_values[mid]) / 2)

    return {
        "days": days,
        "total_requests": len(timeline),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "pending_count": len(pending),
        "approved_but_not_executed_count": len(stalled),
        "execution_failed_count": len(failed),
        "median_approval_to_execution_ms": median_latency,
        "recent_stalled": [_to_decision_summary_item(item) for item in stalled[:10]],
        "recent_failed": [_to_decision_summary_item(item) for item in failed[:10]],
    }


async def get_ai_reliability(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 200,
) -> AiReliability:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(Signal)
        .where(
            Signal.organization_id == org_id,
            Signal.topic.in_([AI_CALL_COMPLETED, AI_CALL_FAILED]),
            Signal.occurred_at >= cutoff,
        )
        .order_by(Signal.occurred_at.desc(), Signal.id.desc())
        .limit(limit)
    )
    rows = list((await db.execute(query)).scalars().all())

    provider_rollup: dict[str, dict[str, int]] = {}
    failure_items: list[AiReliabilityFailure] = []
    total_calls = 0
    failed_calls = 0
    fallback_count = 0
    latency_values: list[int] = []

    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        provider = str(payload.get("provider") or "unknown")
        bucket = provider_rollup.setdefault(
            provider,
            {
                "total_calls": 0,
                "failed_calls": 0,
                "fallback_count": 0,
                "latency_total_ms": 0,
                "latency_count": 0,
            },
        )
        bucket["total_calls"] += 1
        total_calls += 1

        latency_raw = payload.get("latency_ms")
        try:
            latency_ms = int(latency_raw) if latency_raw is not None else None
        except (TypeError, ValueError):
            latency_ms = None
        if latency_ms is not None:
            bucket["latency_total_ms"] += latency_ms
            bucket["latency_count"] += 1
            latency_values.append(latency_ms)

        if bool(payload.get("used_fallback")):
            bucket["fallback_count"] += 1
            fallback_count += 1

        if row.topic == AI_CALL_FAILED:
            bucket["failed_calls"] += 1
            failed_calls += 1
            failure_items.append(
                {
                    "signal_id": row.signal_id,
                    "provider": provider if provider else None,
                    "model_name": str(payload.get("model_name")) if payload.get("model_name") else None,
                    "error_type": str(payload.get("error_type")) if payload.get("error_type") else None,
                    "request_id": str(payload.get("request_id")) if payload.get("request_id") else row.request_id,
                    "fallback_from": str(payload.get("fallback_from")) if payload.get("fallback_from") else None,
                    "latency_ms": latency_ms,
                    "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                }
            )

    providers: list[AiReliabilityProvider] = []
    for provider, bucket in provider_rollup.items():
        provider_total = bucket["total_calls"]
        provider_failed = bucket["failed_calls"]
        provider_fallback = bucket["fallback_count"]
        avg_latency_ms = 0
        if bucket["latency_count"] > 0:
            avg_latency_ms = int(bucket["latency_total_ms"] / bucket["latency_count"])
        providers.append(
            {
                "provider": provider,
                "total_calls": provider_total,
                "failed_calls": provider_failed,
                "fallback_count": provider_fallback,
                "error_rate": round((provider_failed / provider_total) * 100, 1) if provider_total else 0.0,
                "fallback_rate": round((provider_fallback / provider_total) * 100, 1) if provider_total else 0.0,
                "avg_latency_ms": avg_latency_ms,
            }
        )
    providers.sort(key=lambda item: (-item["total_calls"], item["provider"]))

    avg_latency_ms = None
    if latency_values:
        avg_latency_ms = int(sum(latency_values) / len(latency_values))

    return {
        "days": days,
        "total_calls": total_calls,
        "failed_calls": failed_calls,
        "fallback_count": fallback_count,
        "success_rate": round(((total_calls - failed_calls) / total_calls) * 100, 1) if total_calls else 0.0,
        "error_rate": round((failed_calls / total_calls) * 100, 1) if total_calls else 0.0,
        "fallback_rate": round((fallback_count / total_calls) * 100, 1) if total_calls else 0.0,
        "avg_latency_ms": avg_latency_ms,
        "providers": providers,
        "recent_failures": failure_items[:10],
    }


async def get_scheduler_health(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 300,
) -> SchedulerHealth:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(Signal)
        .where(
            Signal.organization_id == org_id,
            Signal.topic.in_([SCHEDULER_JOB_COMPLETED, SCHEDULER_JOB_FAILED]),
            Signal.occurred_at >= cutoff,
        )
        .order_by(Signal.occurred_at.desc(), Signal.id.desc())
        .limit(limit)
    )
    rows = list((await db.execute(query)).scalars().all())

    job_rollup: dict[str, dict[str, object]] = {}
    recent_failures: list[SchedulerHealthFailure] = []
    total_runs = 0
    failed_runs = 0
    duration_values: list[int] = []

    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        job_name = str(payload.get("job_name") or row.entity_id or "unknown")
        bucket = job_rollup.setdefault(
            job_name,
            {
                "total_runs": 0,
                "failed_runs": 0,
                "duration_total_ms": 0,
                "duration_count": 0,
                "last_status": None,
                "last_occurred_at": None,
            },
        )
        bucket["total_runs"] = int(bucket["total_runs"]) + 1
        total_runs += 1

        duration_raw = payload.get("duration_ms")
        try:
            duration_ms = int(duration_raw) if duration_raw is not None else None
        except (TypeError, ValueError):
            duration_ms = None
        if duration_ms is not None:
            bucket["duration_total_ms"] = int(bucket["duration_total_ms"]) + duration_ms
            bucket["duration_count"] = int(bucket["duration_count"]) + 1
            duration_values.append(duration_ms)

        previous_last = bucket.get("last_occurred_at")
        if previous_last is None or (row.occurred_at and row.occurred_at >= previous_last):
            bucket["last_status"] = str(payload.get("status") or "")
            bucket["last_occurred_at"] = row.occurred_at

        if row.topic == SCHEDULER_JOB_FAILED:
            bucket["failed_runs"] = int(bucket["failed_runs"]) + 1
            failed_runs += 1
            recent_failures.append(
                {
                    "signal_id": row.signal_id,
                    "job_name": job_name,
                    "error": str(payload.get("error")) if payload.get("error") else None,
                    "duration_ms": duration_ms,
                    "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                }
            )

    jobs: list[SchedulerHealthJob] = []
    for job_name, bucket in job_rollup.items():
        total_job_runs = int(bucket["total_runs"])
        failed_job_runs = int(bucket["failed_runs"])
        avg_duration_ms = 0
        if int(bucket["duration_count"]) > 0:
            avg_duration_ms = int(int(bucket["duration_total_ms"]) / int(bucket["duration_count"]))
        last_occurred_at = bucket.get("last_occurred_at")
        jobs.append(
            {
                "job_name": job_name,
                "total_runs": total_job_runs,
                "failed_runs": failed_job_runs,
                "success_rate": round(((total_job_runs - failed_job_runs) / total_job_runs) * 100, 1)
                if total_job_runs
                else 0.0,
                "avg_duration_ms": avg_duration_ms,
                "last_status": str(bucket.get("last_status") or "") or None,
                "last_occurred_at": last_occurred_at.isoformat() if last_occurred_at else None,
            }
        )
    jobs.sort(key=lambda item: (-item["failed_runs"], -item["total_runs"], item["job_name"]))

    avg_duration_ms = None
    if duration_values:
        avg_duration_ms = int(sum(duration_values) / len(duration_values))

    return {
        "days": days,
        "total_runs": total_runs,
        "failed_runs": failed_runs,
        "success_rate": round(((total_runs - failed_runs) / total_runs) * 100, 1) if total_runs else 0.0,
        "avg_duration_ms": avg_duration_ms,
        "jobs": jobs,
        "recent_failures": recent_failures[:10],
    }


async def get_webhook_reliability(
    db: AsyncSession,
    *,
    org_id: int,
    days: int = 7,
    limit: int = 300,
) -> WebhookReliability:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(Signal)
        .where(
            Signal.organization_id == org_id,
            Signal.topic.in_([WEBHOOK_DELIVERY_SUCCEEDED, WEBHOOK_DELIVERY_FAILED]),
            Signal.occurred_at >= cutoff,
        )
        .order_by(Signal.occurred_at.desc(), Signal.id.desc())
        .limit(limit)
    )
    rows = list((await db.execute(query)).scalars().all())

    endpoint_rollup: dict[str, dict[str, object]] = {}
    recent_failures: list[WebhookReliabilityFailure] = []
    total_deliveries = 0
    failed_deliveries = 0
    duration_values: list[int] = []

    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        endpoint_raw = payload.get("endpoint_id")
        endpoint_key = str(endpoint_raw) if endpoint_raw is not None else "unknown"
        bucket = endpoint_rollup.setdefault(
            endpoint_key,
            {
                "endpoint_id": None,
                "total_deliveries": 0,
                "failed_deliveries": 0,
                "duration_total_ms": 0,
                "duration_count": 0,
                "last_status": None,
                "last_event": None,
                "last_occurred_at": None,
            },
        )
        try:
            bucket["endpoint_id"] = int(endpoint_raw) if endpoint_raw is not None else None
        except (TypeError, ValueError):
            bucket["endpoint_id"] = None
        bucket["total_deliveries"] = int(bucket["total_deliveries"]) + 1
        total_deliveries += 1

        duration_raw = payload.get("duration_ms")
        try:
            duration_ms = int(duration_raw) if duration_raw is not None else None
        except (TypeError, ValueError):
            duration_ms = None
        if duration_ms is not None:
            bucket["duration_total_ms"] = int(bucket["duration_total_ms"]) + duration_ms
            bucket["duration_count"] = int(bucket["duration_count"]) + 1
            duration_values.append(duration_ms)

        previous_last = bucket.get("last_occurred_at")
        if previous_last is None or (row.occurred_at and row.occurred_at >= previous_last):
            bucket["last_status"] = str(payload.get("status") or "")
            bucket["last_event"] = str(payload.get("event") or "")
            bucket["last_occurred_at"] = row.occurred_at

        if row.topic == WEBHOOK_DELIVERY_FAILED:
            bucket["failed_deliveries"] = int(bucket["failed_deliveries"]) + 1
            failed_deliveries += 1
            status_code_raw = payload.get("response_status_code")
            try:
                status_code = int(status_code_raw) if status_code_raw is not None else None
            except (TypeError, ValueError):
                status_code = None
            recent_failures.append(
                {
                    "signal_id": row.signal_id,
                    "endpoint_id": int(bucket["endpoint_id"]) if bucket["endpoint_id"] is not None else None,
                    "event": str(payload.get("event")) if payload.get("event") else None,
                    "error_message": str(payload.get("error_message")) if payload.get("error_message") else None,
                    "response_status_code": status_code,
                    "duration_ms": duration_ms,
                    "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                }
            )

    endpoints: list[WebhookReliabilityEndpoint] = []
    for bucket in endpoint_rollup.values():
        total_endpoint_deliveries = int(bucket["total_deliveries"])
        failed_endpoint_deliveries = int(bucket["failed_deliveries"])
        avg_duration_ms = 0
        if int(bucket["duration_count"]) > 0:
            avg_duration_ms = int(int(bucket["duration_total_ms"]) / int(bucket["duration_count"]))
        last_occurred_at = bucket.get("last_occurred_at")
        endpoints.append(
            {
                "endpoint_id": int(bucket["endpoint_id"]) if bucket["endpoint_id"] is not None else None,
                "total_deliveries": total_endpoint_deliveries,
                "failed_deliveries": failed_endpoint_deliveries,
                "success_rate": round(
                    ((total_endpoint_deliveries - failed_endpoint_deliveries) / total_endpoint_deliveries) * 100,
                    1,
                )
                if total_endpoint_deliveries
                else 0.0,
                "avg_duration_ms": avg_duration_ms,
                "last_status": str(bucket.get("last_status") or "") or None,
                "last_event": str(bucket.get("last_event") or "") or None,
                "last_occurred_at": last_occurred_at.isoformat() if last_occurred_at else None,
            }
        )
    endpoints.sort(
        key=lambda item: (
            -item["failed_deliveries"],
            -item["total_deliveries"],
            item["endpoint_id"] if item["endpoint_id"] is not None else 10**9,
        )
    )

    avg_duration_ms = None
    if duration_values:
        avg_duration_ms = int(sum(duration_values) / len(duration_values))

    return {
        "days": days,
        "total_deliveries": total_deliveries,
        "failed_deliveries": failed_deliveries,
        "success_rate": round(((total_deliveries - failed_deliveries) / total_deliveries) * 100, 1)
        if total_deliveries
        else 0.0,
        "avg_duration_ms": avg_duration_ms,
        "endpoints": endpoints,
        "recent_failures": recent_failures[:10],
    }
