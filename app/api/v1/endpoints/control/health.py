"""Health, system monitoring, storage metrics, and security posture endpoints."""
from __future__ import annotations

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
from app.models.event import Event
from app.models.integration import Integration
from app.models.task import Task
from app.schemas.control import (
    DataQualityRead,
    HealthSummaryRead,
    IntegrationHealthRead,
    ManagerSLARead,
    SecurityPostureRead,
    StorageMetricsRead,
    SystemHealthDependency,
    SystemHealthRead,
)
from app.services import clone_control, trend_telemetry
from app.services import memory as memory_service
from app.services.ai_router import get_recent_calls_summary

from ._shared import (
    _FEEDBACK_METRICS_WINDOW_DAYS,
    _integration_state,
    _integration_suggested_actions,
    _provider_key_ready,
)

router = APIRouter()


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
        dependencies.append(
            SystemHealthDependency(name="database", status="down", detail=f"probe failed: {type(exc).__name__}")
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
            dependencies.append(
                SystemHealthDependency(name="redis", status="down", detail=f"probe failed: {type(exc).__name__}")
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


@router.get("/trend/metrics")
async def trend_metrics(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict[str, float]:
    return await trend_telemetry.get_trend_metrics(db, org_id=int(actor["org_id"]))


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


@router.post("/backup")
async def create_backup(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Create a database backup (SQLite file copy or pg_dump)."""
    from app.services.db_backup import create_backup as run_backup

    return await run_backup()


@router.get("/backup/list")
async def list_backups(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """List existing database backups."""
    from app.services.db_backup import list_backups as get_backups

    items = get_backups()
    return {"count": len(items), "backups": items}


# ── Cron dead-man switch ─────────────────────────────────────────────────────


@router.get("/cron/health")
async def cron_health(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Dead-man switch: detect silent or failing cron jobs."""
    from app.services.cron_monitor import get_cron_health

    return await get_cron_health(db, org_id=int(actor["org_id"]))
