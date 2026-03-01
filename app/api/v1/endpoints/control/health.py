"""Health, system monitoring, storage metrics, and security posture endpoints."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, validate_startup_settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.core.request_context import get_current_request_id
from app.logs.audit import record_action
from app.models.approval import Approval
from app.models.ceo_control import SchedulerJobRun
from app.models.event import Event
from app.models.integration import Integration
from app.models.task import Task
from app.models.webhook import WebhookDelivery
from app.schemas.control import (
    BackupCreateRead,
    BackupListRead,
    CronHealthRead,
    DataQualityRead,
    HealthSummaryRead,
    IntegrationHealthRead,
    ManagerSLARead,
    SchedulerSLORead,
    SecurityPostureRead,
    StorageMetricsRead,
    SystemHealthDependency,
    SystemHealthRead,
    TrendMetricsRead,
    WebhookReliabilityRead,
)
from app.services import clone_control, trend_telemetry
from app.services import memory as memory_service
from app.services import webhook as webhook_service
from app.services.ai_router import get_recent_calls_summary

from ._shared import (
    _FEEDBACK_METRICS_WINDOW_DAYS,
    _integration_state,
    _integration_suggested_actions,
    _provider_key_ready,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health-summary", response_model=HealthSummaryRead)
async def health_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> HealthSummaryRead:
    org_id = int(actor["org_id"])
    open_tasks = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.organization_id == org_id,
                Task.is_done.is_(False),
            )
        )
    ).scalar_one()
    pending_approvals = (
        await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == org_id,
                Approval.status == "pending",
            )
        )
    ).scalar_one()
    connected_integrations = (
        await db.execute(
            select(func.count(Integration.id)).where(
                Integration.organization_id == org_id,
                Integration.status == "connected",
            )
        )
    ).scalar_one()
    failing_integrations = (
        await db.execute(
            select(func.count(Integration.id)).where(
                Integration.organization_id == org_id,
                Integration.status == "connected",
                Integration.last_sync_status == "error",
            )
        )
    ).scalar_one()
    return HealthSummaryRead(
        open_tasks=int(open_tasks or 0),
        pending_approvals=int(pending_approvals or 0),
        connected_integrations=int(connected_integrations or 0),
        failing_integrations=int(failing_integrations or 0),
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.get("/integrations/health", response_model=IntegrationHealthRead)
async def integrations_health(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> IntegrationHealthRead:
    org_id = int(actor["org_id"])
    now = datetime.now(UTC)
    stale_hours = int(settings.SYNC_STALE_HOURS)
    cutoff = now.timestamp() - (stale_hours * 3600)
    rows = (
        await db.execute(
            select(Integration).where(
                Integration.organization_id == org_id,
                Integration.status == "connected",
            )
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        age_hours: float | None = None
        if row.last_sync_at:
            age_hours = round((now - row.last_sync_at).total_seconds() / 3600, 2)
        stale = bool(row.last_sync_at is None or row.last_sync_at.timestamp() < cutoff or row.last_sync_status == "error")
        state = _integration_state(
            connected=(row.status == "connected"),
            last_sync_status=row.last_sync_status,
            last_sync_at=row.last_sync_at,
            now=now,
            stale_hours=stale_hours,
        )
        items.append(
            {
                "type": row.type,
                "connected": row.status == "connected",
                "state": state,
                "last_sync_status": row.last_sync_status,
                "last_sync_at": row.last_sync_at,
                "stale": stale,
                "age_hours": age_hours,
                "suggested_actions": _integration_suggested_actions(
                    integration_type=row.type,
                    state=state,
                    last_sync_status=row.last_sync_status,
                    age_hours=age_hours,
                    stale_hours=stale_hours,
                ),
            }
        )
    return IntegrationHealthRead(
        generated_at=now,
        stale_hours_threshold=stale_hours,
        total_connected=len(items),
        failing_count=sum(1 for x in items if x.get("last_sync_status") == "error"),
        stale_count=sum(1 for x in items if x.get("stale")),
        items=items,  # type: ignore[arg-type]
    )


@router.get("/system-health", response_model=SystemHealthRead)
async def system_health(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SystemHealthRead:
    now = datetime.now(UTC)
    dependencies: list[SystemHealthDependency] = []

    # Database probe
    try:
        await db.execute(text("SELECT 1"))
        dependencies.append(SystemHealthDependency(name="database", status="ok", detail="reachable"))
    except (SQLAlchemyError, RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        logger.warning("health probe: database down: %s", type(exc).__name__, exc_info=True)
        dependencies.append(
            SystemHealthDependency(name="database", status="down", detail="probe failed")
        )

    # Redis (optional)
    redis_url = (settings.RATE_LIMIT_REDIS_URL or settings.IDEMPOTENCY_REDIS_URL or "").strip()
    if not redis_url:
        dependencies.append(
            SystemHealthDependency(name="redis", status="not_configured", detail="RATE_LIMIT_REDIS_URL/IDEMPOTENCY_REDIS_URL not set")
        )
    else:
        try:
            import redis.asyncio as redis

            client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
            pong = await client.ping()
            await client.aclose()
            dependencies.append(
                SystemHealthDependency(
                    name="redis",
                    status="ok" if pong else "degraded",
                    detail="ping ok" if pong else "ping returned falsy",
                )
            )
        except (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError, ImportError, AttributeError) as exc:
            logger.warning("health probe: redis down: %s", type(exc).__name__, exc_info=True)
            dependencies.append(
                SystemHealthDependency(name="redis", status="down", detail="probe failed")
            )

    # Vector store (this project uses DB-backed storage by default)
    dependencies.append(
        SystemHealthDependency(name="vector_store", status="ok", detail="database-backed")
    )

    # AI provider readiness
    provider_keys = {
        "openai": settings.OPENAI_API_KEY,
        "anthropic": settings.ANTHROPIC_API_KEY,
        "groq": settings.GROQ_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }
    ai_ready_count = 0
    for provider_name, api_key in provider_keys.items():
        if _provider_key_ready(api_key):
            ai_ready_count += 1
            dependencies.append(
                SystemHealthDependency(name=provider_name, status="ok", detail="api key configured")
            )
        else:
            dependencies.append(
                SystemHealthDependency(
                    name=provider_name,
                    status="not_configured",
                    detail="api key missing or placeholder",
                )
            )
    dependencies.append(
        SystemHealthDependency(
            name="ai_router",
            status="ok" if ai_ready_count > 0 else "degraded",
            detail=f"{ai_ready_count}/4 providers configured",
        )
    )

    integration_health = await integrations_health(db=db, actor=actor)
    if any(item.state == "degraded" for item in integration_health.items):
        dependencies.append(SystemHealthDependency(name="integrations", status="degraded", detail="one or more sync failures"))
    elif any(item.state in {"stale", "down"} for item in integration_health.items):
        dependencies.append(SystemHealthDependency(name="integrations", status="degraded", detail="one or more integrations stale/down"))
    else:
        dependencies.append(SystemHealthDependency(name="integrations", status="ok", detail="all connected integrations healthy"))

    status_values = [d.status for d in dependencies]
    if "down" in status_values:
        overall_status = "down"
    elif "degraded" in status_values:
        overall_status = "degraded"
    else:
        overall_status = "ok"
    await record_action(
        db,
        event_type="system_health_checked",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="control",
        entity_id=None,
        payload_json={
            "request_id": get_current_request_id(),
            "overall_status": overall_status,
            "dependency_count": len(dependencies),
        },
    )
    return SystemHealthRead(
        generated_at=now,
        overall_status=overall_status,  # type: ignore[arg-type]
        dependencies=dependencies,
        integrations=integration_health,
    )


@router.get("/storage/metrics", response_model=StorageMetricsRead)
async def storage_metrics(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> StorageMetricsRead:
    ai_summary = get_recent_calls_summary(window_seconds=3600)
    total_calls = ai_summary.get("total_calls", 0)
    fallback_rate = ai_summary.get("fallback_rate", 0.0)
    error_count = ai_summary.get("error_count", 0)
    provider_counts_raw = ai_summary.get("provider_counts", {})
    provider_counts = provider_counts_raw if isinstance(provider_counts_raw, dict) else {}
    feedback_cutoff = datetime.now(UTC) - timedelta(days=_FEEDBACK_METRICS_WINDOW_DAYS)
    feedback_counts = (
        await db.execute(
            select(Event.event_type, func.count(Event.id))
            .where(
                Event.organization_id == int(actor["org_id"]),
                Event.event_type.in_(["approval_feedback_recorded", "approval_feedback_failed"]),
                Event.created_at >= feedback_cutoff,
            )
            .group_by(Event.event_type)
        )
    ).all()
    feedback_map = {str(k): int(v) for k, v in feedback_counts}
    feedback_succeeded = feedback_map.get("approval_feedback_recorded", 0)
    feedback_failed = feedback_map.get("approval_feedback_failed", 0)
    feedback_attempted = feedback_succeeded + feedback_failed
    feedback_success_rate = round((feedback_succeeded / feedback_attempted), 4) if feedback_attempted else 1.0
    return StorageMetricsRead(
        generated_at=datetime.now(UTC),
        memory_context_cache=memory_service.get_memory_cache_stats(),
        ai_router_recent_calls_1h=int(total_calls) if isinstance(total_calls, int | float) else 0,
        ai_router_fallback_rate_1h=float(fallback_rate) if isinstance(fallback_rate, int | float) else 0.0,
        ai_router_errors_1h=int(error_count) if isinstance(error_count, int | float) else 0,
        ai_router_provider_counts_1h={str(k): int(v) for k, v in provider_counts.items() if isinstance(v, int)},
        approval_feedback_stats={
            "attempted": feedback_attempted,
            "succeeded": feedback_succeeded,
            "failed": feedback_failed,
            "success_rate": feedback_success_rate,
            "window_days": _FEEDBACK_METRICS_WINDOW_DAYS,
        },
    )


@router.get("/trend/metrics", response_model=TrendMetricsRead)
async def trend_metrics(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> TrendMetricsRead:
    data = await trend_telemetry.get_trend_metrics(db, org_id=int(actor["org_id"]))
    return TrendMetricsRead(**data)


@router.get("/scheduler/slo", response_model=SchedulerSLORead)
async def scheduler_slo(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SchedulerSLORead:
    org_id = int(actor["org_id"])
    now = datetime.now(UTC)
    rows = (
        (
            await db.execute(
                select(SchedulerJobRun).where(
                    SchedulerJobRun.organization_id == org_id,
                    SchedulerJobRun.started_at >= (now - timedelta(hours=24)),
                )
            )
        )
        .scalars()
        .all()
    )
    total = len(rows)
    ok = sum(1 for row in rows if str(row.status) == "ok")
    success_rate = round((ok / total), 4) if total else 1.0
    durations = sorted(int(row.duration_ms or 0) for row in rows if row.duration_ms is not None)
    p95_ms = durations[min(len(durations) - 1, int(0.95 * (len(durations) - 1)))] if durations else 0
    stale_runs = sum(
        1
        for row in rows
        if row.finished_at is None and (now - row.started_at).total_seconds() > 1800
    )
    error_type_counts: dict[str, int] = {}
    for row in rows:
        if str(row.status) == "ok":
            continue
        raw_error = str(row.error or "").strip()
        error_type = raw_error.split(":", 1)[0].strip() if raw_error else "unknown"
        if not error_type:
            error_type = "unknown"
        error_type_counts[error_type] = int(error_type_counts.get(error_type, 0)) + 1
    breached = bool(success_rate < 0.97 or p95_ms > 30_000 or stale_runs > 0)
    return SchedulerSLORead(
        window_hours=24,
        total_runs=total,
        success_rate=success_rate,
        p95_duration_ms=p95_ms,
        stale_runs=stale_runs,
        slo_breached=breached,
        error_type_counts=error_type_counts,
    )


@router.get("/webhook/reliability", response_model=WebhookReliabilityRead)
async def webhook_reliability(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> WebhookReliabilityRead:
    org_id = int(actor["org_id"])
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=24)
    rows = (
        (
            await db.execute(
                select(WebhookDelivery).where(
                    WebhookDelivery.organization_id == org_id,
                    WebhookDelivery.created_at >= window_start,
                )
            )
        )
        .scalars()
        .all()
    )
    rows_by_endpoint: dict[int, list[WebhookDelivery]] = {}
    for row in rows:
        endpoint_id = int(getattr(row, "webhook_endpoint_id", 0) or 0)
        rows_by_endpoint.setdefault(endpoint_id, []).append(row)
    for endpoint_rows in rows_by_endpoint.values():
        endpoint_rows.sort(key=lambda item: item.created_at)

    replay_success_count = 0
    for row in rows:
        if str(row.status) != "replayed":
            continue
        endpoint_rows = rows_by_endpoint.get(int(row.webhook_endpoint_id), [])
        replay_target = next(
            (
                candidate
                for candidate in endpoint_rows
                if candidate.created_at > row.created_at and candidate.event == row.event and str(candidate.status) == "success"
            ),
            None,
        )
        if replay_target is not None:
            replay_success_count += 1

    error_category_counts: dict[str, int] = {}
    for row in rows:
        if str(row.status) not in {"failed", "dead_letter"}:
            continue
        category = webhook_service.classify_delivery_error(
            row.error_message,
            int(row.response_status_code) if row.response_status_code is not None else None,
        )
        error_category_counts[category] = int(error_category_counts.get(category, 0)) + 1

    return WebhookReliabilityRead(
        window_hours=24,
        total_deliveries=len(rows),
        success_count=sum(1 for row in rows if str(row.status) == "success"),
        failed_count=sum(1 for row in rows if str(row.status) == "failed"),
        dead_letter_count=sum(1 for row in rows if str(row.status) == "dead_letter"),
        replayed_original_count=sum(1 for row in rows if str(row.status) == "replayed"),
        replay_success_count=replay_success_count,
        error_category_counts=error_category_counts,
    )


@router.get("/security/posture", response_model=SecurityPostureRead)
async def security_posture(
    _db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SecurityPostureRead:
    now = datetime.now(UTC)
    issues = validate_startup_settings(settings)
    return SecurityPostureRead(
        generated_at=now,
        status="ok" if not issues else "needs_attention",
        premium_mode=bool(settings.SECURITY_PREMIUM_MODE),
        privacy_profile=settings.PRIVACY_POLICY_PROFILE,
        legal_terms_version=(settings.LEGAL_TERMS_VERSION or None),
        account_mfa_required=bool(settings.ACCOUNT_MFA_REQUIRED),
        account_sso_required=bool(settings.ACCOUNT_SSO_REQUIRED),
        account_session_max_hours=int(settings.ACCOUNT_SESSION_MAX_HOURS),
        marketing_export_pii_allowed=bool(settings.MARKETING_EXPORT_PII_ALLOWED),
        open_issues=issues,
    )


@router.get("/data-quality", response_model=DataQualityRead)
async def data_quality(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DataQualityRead:
    data = await clone_control.data_quality_snapshot(db, organization_id=int(actor["org_id"]))
    return DataQualityRead(**data)  # type: ignore[arg-type]


@router.get("/sla/manager", response_model=ManagerSLARead)
async def manager_sla(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ManagerSLARead:
    data = await clone_control.manager_sla_snapshot(db, organization_id=int(actor["org_id"]))
    return ManagerSLARead(**data)  # type: ignore[arg-type]


# ── Database backup ──────────────────────────────────────────────────────────


@router.post("/backup", response_model=BackupCreateRead)
async def create_backup(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> BackupCreateRead:
    """Create a database backup (SQLite file copy or pg_dump)."""
    from app.services.db_backup import create_backup as run_backup

    data = await run_backup()
    return BackupCreateRead(**data)


@router.get("/backup/list", response_model=BackupListRead)
async def list_backups(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> BackupListRead:
    """List existing database backups."""
    import asyncio

    from app.services.db_backup import list_backups as get_backups

    items = await asyncio.to_thread(get_backups)
    return BackupListRead(count=len(items), backups=items)


# ── Cron dead-man switch ─────────────────────────────────────────────────────


@router.get("/cron/health", response_model=CronHealthRead)
async def cron_health(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CronHealthRead:
    """Dead-man switch: detect silent or failing cron jobs."""
    from app.services.cron_monitor import get_cron_health

    data = await get_cron_health(db, org_id=int(actor["org_id"]))
    return CronHealthRead(**data)
