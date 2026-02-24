from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, validate_startup_settings
from app.core.deps import get_db
from app.core.request_context import get_current_request_id
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.models.approval import Approval
from app.models.ceo_control import (
    ClickUpTaskSnapshot,
    DigitalOceanCostSnapshot,
    DigitalOceanDropletSnapshot,
    GitHubIdentityMap,
    GitHubPRSnapshot,
    GitHubRepoSnapshot,
    SchedulerJobRun,
)
from app.models.integration import Integration
from app.models.task import Task
from app.schemas.control import (
    BrainTrainRead,
    BrainTrainRequest,
    CEOMorningBriefRead,
    CEOStatusRead,
    ComplianceReportRead,
    ComplianceRunRead,
    DataQualityRead,
    ExecutePlanRead,
    ExecutePlanRequest,
    FounderPlaybookRead,
    GitHubIdentityMapListRead,
    GitHubIdentityMapUpsertRead,
    GitHubIdentityMapUpsertRequest,
    HealthSummaryRead,
    IntegrationHealthRead,
    ManagerSLARead,
    MessageDraftRead,
    MessageDraftRequest,
    MultiOrgCockpitRead,
    MultiOrgCockpitOrgRead,
    SchedulerJobRunListRead,
    SchedulerReplayRead,
    SchedulerReplayRequest,
    ScenarioSimulationRead,
    ScenarioSimulationRequest,
    SecurityPostureRead,
    SystemHealthDependency,
    SystemHealthRead,
    WeeklyBoardPacketRead,
)
from app.services import clone_brain, clone_control, compliance_engine, email_control, organization as organization_service
from app.services import metrics_service, signal_ingestion
from app.services import sync_scheduler

router = APIRouter(prefix="/control", tags=["CEO Control"])


def _integration_state(
    *,
    connected: bool,
    last_sync_status: str | None,
    last_sync_at: datetime | None,
    now: datetime,
    stale_hours: int,
) -> str:
    if not connected:
        return "down"
    if last_sync_status == "error":
        return "degraded"
    if last_sync_at is None:
        return "degraded"
    age_hours = (now - last_sync_at).total_seconds() / 3600
    if age_hours >= stale_hours:
        return "stale"
    return "healthy"


def _integration_suggested_actions(
    *,
    integration_type: str,
    state: str,
    last_sync_status: str | None,
    age_hours: float | None,
    stale_hours: int,
) -> list[str]:
    actions: list[str] = []
    if state == "down":
        actions.append(f"Connect {integration_type} using /api/v1/integrations/{integration_type}/connect.")
        return actions
    if last_sync_status == "error":
        actions.append(f"Run /api/v1/integrations/{integration_type}/status and verify token/scopes.")
        actions.append(f"Replay sync via /api/v1/integrations/{integration_type}/sync.")
    if state == "stale":
        actions.append(f"Sync is stale ({age_hours or 'unknown'}h). Run /api/v1/integrations/{integration_type}/sync.")
    if state == "degraded" and last_sync_status != "error":
        actions.append("Connection exists but health is degraded; run status + sync to refresh metadata.")
    if not actions:
        actions.append(f"{integration_type} integration is healthy; keep hourly sync enabled.")
    if age_hours is not None and age_hours >= (stale_hours * 2):
        actions.append("Escalate to owner if stale over 2x SLA window.")
    return actions[:3]


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
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _top_prs_waiting_sharon(prs: list[GitHubPRSnapshot]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pr in prs:
        reviewers = [x.lower() for x in json.loads(pr.requested_reviewers or "[]")]
        if "sharon" in " ".join(reviewers):
            rows.append(
                {
                    "repo_name": pr.repo_name,
                    "pr_number": pr.pr_number,
                    "title": pr.title,
                    "author": pr.author,
                    "url": pr.url,
                }
            )
    return rows[:10]


@router.get("/ceo/status", response_model=CEOStatusRead)
async def ceo_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CEOStatusRead:
    org_id = int(actor["org_id"])

    tasks = (
        await db.execute(
            select(ClickUpTaskSnapshot)
            .where(ClickUpTaskSnapshot.organization_id == org_id)
            .order_by(ClickUpTaskSnapshot.synced_at.desc())
            .limit(200)
        )
    ).scalars().all()
    overdue = []
    now = datetime.now(timezone.utc)
    for t in tasks:
        if t.due_date and t.due_date < now and (t.status or "").lower() not in {"done", "complete", "closed"}:
            overdue.append({"task_id": t.external_id, "name": t.name, "due_date": t.due_date.isoformat()})

    prs = (
        await db.execute(
            select(GitHubPRSnapshot)
            .where(GitHubPRSnapshot.organization_id == org_id)
            .order_by(GitHubPRSnapshot.synced_at.desc())
            .limit(200)
        )
    ).scalars().all()
    repos = (
        await db.execute(
            select(GitHubRepoSnapshot)
            .where(GitHubRepoSnapshot.organization_id == org_id)
            .order_by(GitHubRepoSnapshot.synced_at.desc())
            .limit(200)
        )
    ).scalars().all()
    branch_issues = [
        {
            "repo_name": r.repo_name,
            "is_protected": r.is_protected,
            "requires_reviews": r.requires_reviews,
            "required_checks_enabled": r.required_checks_enabled,
        }
        for r in repos
        if (not r.is_protected) or (not r.requires_reviews) or (not r.required_checks_enabled)
    ][:20]
    droplets = (
        await db.execute(
            select(DigitalOceanDropletSnapshot)
            .where(DigitalOceanDropletSnapshot.organization_id == org_id)
            .order_by(DigitalOceanDropletSnapshot.synced_at.desc())
            .limit(200)
        )
    ).scalars().all()
    infra_risks = [
        {
            "droplet_id": d.droplet_id,
            "name": d.name,
            "status": d.status,
            "backups_enabled": d.backups_enabled,
        }
        for d in droplets
        if d.status == "active" and d.backups_enabled is False
    ][:20]

    costs = (
        await db.execute(
            select(DigitalOceanCostSnapshot)
            .where(DigitalOceanCostSnapshot.organization_id == org_id)
            .order_by(DigitalOceanCostSnapshot.synced_at.desc())
            .limit(2)
        )
    ).scalars().all()
    cost_alerts: list[dict[str, Any]] = []
    if len(costs) >= 2 and costs[0].amount_usd is not None and costs[1].amount_usd:
        latest = float(costs[0].amount_usd)
        previous = float(costs[1].amount_usd)
        if previous > 0:
            delta_pct = ((latest - previous) / previous) * 100.0
            if delta_pct > 30:
                cost_alerts.append(
                    {
                        "platform": "digitalocean",
                        "latest_amount_usd": round(latest, 2),
                        "previous_amount_usd": round(previous, 2),
                        "delta_percent": round(delta_pct, 1),
                        "title": "Cost spike > 30% vs previous snapshot",
                    }
                )

    return CEOStatusRead(
        top_overdue_critical_tasks=overdue[:10],
        prs_waiting_sharon_review=_top_prs_waiting_sharon(prs),
        branch_protection_issues=branch_issues,
        infra_risks=infra_risks,
        cost_alerts=cost_alerts,
        mode="suggest_only",
    )


@router.get("/integrations/health", response_model=IntegrationHealthRead)
async def integrations_health(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> IntegrationHealthRead:
    org_id = int(actor["org_id"])
    now = datetime.now(timezone.utc)
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
        items=items,
    )


@router.get("/system-health", response_model=SystemHealthRead)
async def system_health(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SystemHealthRead:
    now = datetime.now(timezone.utc)
    dependencies: list[SystemHealthDependency] = []

    # Database probe
    try:
        await db.execute(text("SELECT 1"))
        dependencies.append(SystemHealthDependency(name="database", status="ok", detail="reachable"))
    except Exception as exc:
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
            import redis.asyncio as redis  # type: ignore[import-untyped]

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
        except Exception as exc:
            dependencies.append(
                SystemHealthDependency(name="redis", status="down", detail=f"probe failed: {type(exc).__name__}")
            )

    # Vector store (this project uses DB-backed storage by default)
    dependencies.append(
        SystemHealthDependency(name="vector_store", status="ok", detail="database-backed")
    )

    # AI key readiness
    if (settings.OPENAI_API_KEY or "").strip():
        dependencies.append(SystemHealthDependency(name="openai", status="ok", detail="api key configured"))
    else:
        dependencies.append(SystemHealthDependency(name="openai", status="degraded", detail="OPENAI_API_KEY missing"))

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
        overall_status=overall_status,
        dependencies=dependencies,
        integrations=integration_health,
    )


@router.get("/security/posture", response_model=SecurityPostureRead)
async def security_posture(
    _db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SecurityPostureRead:
    now = datetime.now(timezone.utc)
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


@router.post("/compliance/run", response_model=ComplianceRunRead)
async def compliance_run(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ComplianceRunRead:
    org_id = int(actor["org_id"])
    request_id = get_current_request_id()
    try:
        result = await compliance_engine.run_compliance(db, org_id)
        await record_action(
            db,
            event_type="compliance_run",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="control",
            entity_id=None,
            payload_json={
                "request_id": request_id,
                "status": "ok",
                "violation_count": len(result["violations"]),
                "compliance_score": int(result["compliance_score"]),
            },
        )
        return ComplianceRunRead(ok=True, compliance_score=int(result["compliance_score"]), violations=result["violations"], mode="suggest_only")
    except Exception as exc:
        await record_action(
            db,
            event_type="compliance_run",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="control",
            entity_id=None,
            payload_json={
                "request_id": request_id,
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise


@router.get("/compliance/report", response_model=ComplianceReportRead)
async def compliance_report(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ComplianceReportRead:
    org_id = int(actor["org_id"])
    data = await compliance_engine.latest_report(db, org_id)
    return ComplianceReportRead(**data)


@router.post("/message-draft", response_model=MessageDraftRead)
async def message_draft(
    payload: MessageDraftRequest,
    _db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MessageDraftRead:
    to = str(payload.to or "").strip().lower()
    topic = str(payload.topic or "Compliance follow-up")
    violations = payload.violations or []

    intro = "Hi Sharon," if to == "sharon" else "Hi Mano,"
    bullet_lines = []
    for item in violations[:8]:
        if isinstance(item, dict):
            bullet_lines.append(f"- {item.get('title', 'Issue')} ({item.get('severity', 'MED')})")
    if not bullet_lines:
        bullet_lines.append("- Please review the latest compliance dashboard.")

    checklist = [
        "Confirm owners/permissions align with company hierarchy.",
        "Acknowledge each open violation with ETA.",
        "Post update in leadership channel after completion.",
    ]
    text = "\n".join(
        [
            intro,
            "",
            f"Topic: {topic}",
            "Please review and action the following:",
            *bullet_lines,
            "",
            "This is suggest-only guidance; no automatic enforcement actions were taken.",
        ]
    )
    return MessageDraftRead(to=to, message=text, checklist=checklist)


@router.get("/github-identity-map", response_model=GitHubIdentityMapListRead)
async def github_identity_map_list(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> GitHubIdentityMapListRead:
    org_id = int(actor["org_id"])
    rows = (
        await db.execute(
            select(GitHubIdentityMap)
            .where(GitHubIdentityMap.organization_id == org_id)
            .order_by(GitHubIdentityMap.company_email.asc())
        )
    ).scalars().all()
    return GitHubIdentityMapListRead(
        count=len(rows),
        items=[
            {
                "company_email": row.company_email,
                "github_login": row.github_login,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ],
    )


@router.post("/github-identity-map/upsert", response_model=GitHubIdentityMapUpsertRead)
async def github_identity_map_upsert(
    payload: GitHubIdentityMapUpsertRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubIdentityMapUpsertRead:
    org_id = int(actor["org_id"])
    company_email = payload.company_email.strip().lower()
    github_login = payload.github_login.strip().lower()
    now = datetime.now(timezone.utc)

    existing = (
        await db.execute(
            select(GitHubIdentityMap).where(
                GitHubIdentityMap.organization_id == org_id,
                GitHubIdentityMap.company_email == company_email,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.github_login = github_login
        existing.updated_at = now
    else:
        db.add(
            GitHubIdentityMap(
                organization_id=org_id,
                company_email=company_email,
                github_login=github_login,
                created_at=now,
                updated_at=now,
            )
        )
    await db.commit()
    return GitHubIdentityMapUpsertRead(ok=True, company_email=company_email, github_login=github_login)


@router.get("/jobs/runs", response_model=SchedulerJobRunListRead)
async def scheduler_job_runs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SchedulerJobRunListRead:
    org_id = int(actor["org_id"])
    safe_limit = max(1, min(limit, 200))
    rows = (
        await db.execute(
            select(SchedulerJobRun)
            .where(SchedulerJobRun.organization_id == org_id)
            .order_by(SchedulerJobRun.started_at.desc())
            .limit(safe_limit)
        )
    ).scalars().all()
    runs_by_job: dict[str, list[SchedulerJobRun]] = {}
    for row in rows:
        runs_by_job.setdefault(row.job_name, []).append(row)
    items: list[dict[str, Any]] = []
    for row in rows:
        job_runs = sorted(runs_by_job.get(row.job_name, []), key=lambda r: r.started_at, reverse=True)
        failure_streak = 0
        for run in job_runs:
            if run.status == "error":
                failure_streak += 1
            else:
                break
        retry_backoff_seconds: int | None = None
        suggested_next_retry_at: datetime | None = None
        if row.status == "error":
            backoff_seconds = min(3600, 60 * (2 ** max(0, failure_streak - 1)))
            retry_backoff_seconds = backoff_seconds
            suggested_next_retry_at = row.started_at + timedelta(seconds=backoff_seconds)
        dead_letter_candidate = bool(row.status == "error" and failure_streak >= 3)
        items.append(
            {
                "id": row.id,
                "job_name": row.job_name,
                "status": row.status,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "duration_ms": row.duration_ms,
                "details": json.loads(row.details_json or "{}"),
                "error": row.error,
                "failure_streak": failure_streak,
                "retry_backoff_seconds": retry_backoff_seconds,
                "suggested_next_retry_at": suggested_next_retry_at,
                "dead_letter_candidate": dead_letter_candidate,
            }
        )
    return SchedulerJobRunListRead(count=len(items), items=items)


@router.post("/jobs/replay", response_model=SchedulerReplayRead)
async def scheduler_job_replay(
    payload: SchedulerReplayRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SchedulerReplayRead:
    org_id = int(actor["org_id"])
    result = await sync_scheduler.replay_job_for_org(db, org_id, payload.job_name)
    return SchedulerReplayRead(
        ok=bool(result.get("ok")),
        job_name=str(result.get("job_name") or payload.job_name),
        result=result.get("result") if isinstance(result.get("result"), dict) else None,
        error=str(result.get("error")) if result.get("error") else None,
    )


@router.post("/execute-plan", response_model=ExecutePlanRead)
async def execute_plan(
    payload: ExecutePlanRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ExecutePlanRead:
    org_id = int(actor["org_id"])
    sync_result = await sync_scheduler.replay_job_for_org(db, org_id, "full_sync")
    email_result = await email_control.process_inbox_controls(
        db,
        org_id=org_id,
        actor_user_id=int(actor["id"]),
        limit=100,
    )
    compliance = await compliance_engine.run_compliance(db, org_id)
    challenge = (payload.challenge or "Complex execution dispatch").strip()
    dispatch = await clone_brain.build_dispatch_plan(
        db,
        organization_id=org_id,
        challenge=challenge,
        week_start_date=(payload.week_start_date.date() if payload.week_start_date else None),
        top_n=3,
    )
    quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)
    return ExecutePlanRead(
        ok=True,
        sync=sync_result,
        email_control=email_result,
        compliance={"score": compliance.get("compliance_score"), "violations": len(compliance.get("violations", []))},
        dispatch_plan=dispatch,
        data_quality={
            "missing_identity_count": quality["missing_identity_count"],
            "stale_metrics_count": quality["stale_metrics_count"],
            "duplicate_identity_conflicts": quality["duplicate_identity_conflicts"],
            "orphan_approval_count": quality["orphan_approval_count"],
        },
    )


@router.post("/brain/train-data-driven", response_model=BrainTrainRead)
async def brain_train_data_driven(
    payload: BrainTrainRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> BrainTrainRead:
    org_id = int(actor["org_id"])
    data_collection: dict[str, Any] = {}
    for name, fn in [
        ("clickup", signal_ingestion.ingest_clickup_signals),
        ("github", signal_ingestion.ingest_github_signals),
        ("github_cicd", signal_ingestion.ingest_github_cicd_signals),
        ("gmail", signal_ingestion.ingest_gmail_signals),
    ]:
        try:
            data_collection[name] = await fn(db, org_id)
        except Exception as exc:
            data_collection[name] = {"ok": False, "error": type(exc).__name__}

    metrics: dict[str, Any]
    try:
        metrics_result = await metrics_service.compute_weekly_metrics(db, org_id, weeks=payload.weeks)
        metrics = metrics_result if isinstance(metrics_result, dict) else {"ok": True}
    except Exception as exc:
        metrics = {"ok": False, "error": type(exc).__name__}

    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())
    clone_training = await clone_brain.train_weekly_clone_scores(
        db,
        organization_id=org_id,
        week_start_date=week_start,
    )
    clone_summary = await clone_brain.clone_org_summary(
        db,
        organization_id=org_id,
        week_start_date=week_start,
    )
    dispatch = await clone_brain.build_dispatch_plan(
        db,
        organization_id=org_id,
        challenge=payload.challenge,
        week_start_date=week_start,
        top_n=5,
    )
    data_quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)

    avg_score_raw = clone_summary.get("avg_score", 0.0)
    avg_score = float(avg_score_raw) if isinstance(avg_score_raw, (int, float)) else 0.0
    missing_identity_raw = data_quality.get("missing_identity_count", 0)
    missing_identity_count = int(missing_identity_raw) if isinstance(missing_identity_raw, int) else 0
    ceo_brain = {
        "challenge": payload.challenge,
        "strict_data_driven_mode": True,
        "avg_clone_score": avg_score,
        "dispatch_top_owners": [item.get("employee_name") for item in dispatch[:3]],
        "training_priorities": [
            "Close missing identity maps before expanding autonomous workflows."
            if missing_identity_count > 0
            else "Maintain identity map coverage across all active employees.",
            "Coach low-readiness clones with weekly measurable drills.",
            "Review metrics weekly and only scale strategies with proven outcomes.",
        ],
        "confidence": max(0.0, min(1.0, round((avg_score / 100.0) + 0.15, 2))),
    }

    return BrainTrainRead(
        ok=True,
        mode="suggest_only",
        data_collection=data_collection,
        metrics=metrics,
        clone_training={
            **clone_training,
            "summary": clone_summary,
            "dispatch": dispatch,
        },
        ceo_brain=ceo_brain,
    )


@router.get("/data-quality", response_model=DataQualityRead)
async def data_quality(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DataQualityRead:
    data = await clone_control.data_quality_snapshot(db, organization_id=int(actor["org_id"]))
    return DataQualityRead(**data)


@router.get("/sla/manager", response_model=ManagerSLARead)
async def manager_sla(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ManagerSLARead:
    data = await clone_control.manager_sla_snapshot(db, organization_id=int(actor["org_id"]))
    return ManagerSLARead(**data)


@router.post("/scenario/simulate", response_model=ScenarioSimulationRead)
async def scenario_simulate(
    payload: ScenarioSimulationRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ScenarioSimulationRead:
    org_id = int(actor["org_id"])
    summary = await clone_brain.clone_org_summary(
        db,
        organization_id=org_id,
        week_start_date=None,
    )
    avg_score_raw = summary.get("avg_score", 0.0)
    avg_score = float(avg_score_raw) if isinstance(avg_score_raw, (int, float)) else 0.0
    dispatch = await clone_brain.build_dispatch_plan(
        db,
        organization_id=org_id,
        challenge=payload.challenge,
        week_start_date=None,
        top_n=payload.top_n,
    )
    baseline = max(5.0, min(95.0, 100.0 - avg_score))
    dispatch_avg = 0.0
    if dispatch:
        dispatch_avg = sum(float(item.get("overall_score", 0.0)) for item in dispatch) / len(dispatch)
    projected = max(1.0, baseline - ((dispatch_avg / 100.0) * payload.blockers_count * 2.5))
    drop_pct = round(((baseline - projected) / baseline) * 100.0, 2) if baseline > 0 else 0.0
    return ScenarioSimulationRead(
        challenge=payload.challenge,
        blockers_count=payload.blockers_count,
        baseline_risk_score=round(baseline, 2),
        projected_risk_score=round(projected, 2),
        projected_risk_drop_percent=drop_pct,
        recommended_dispatch=dispatch,
    )


@router.get("/weekly-board-packet", response_model=WeeklyBoardPacketRead)
async def weekly_board_packet(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WeeklyBoardPacketRead:
    org_id = int(actor["org_id"])
    now = datetime.now(timezone.utc)
    week_start = (now.date().isoformat())
    compliance = await compliance_engine.latest_report(db, org_id)
    clone_summary = await clone_brain.clone_org_summary(db, organization_id=org_id, week_start_date=None)
    sla = await clone_control.manager_sla_snapshot(db, organization_id=org_id)
    quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)
    top_actions = [
        "Close HIGH/CRITICAL violations first.",
        "Resolve missing identity mappings for active employees.",
        "Clear pending approval SLA breaches.",
    ]
    return WeeklyBoardPacketRead(
        generated_at=now,
        week_start=week_start,
        compliance={"open_violations": int(compliance.get("count", 0))},
        clone_summary=clone_summary,
        sla={
            "missing_reports": sla["missing_reports"],
            "pending_approvals_breached": sla["pending_approvals_breached"],
            "status": sla["status"],
        },
        data_quality={
            "missing_identity_count": quality["missing_identity_count"],
            "stale_metrics_count": quality["stale_metrics_count"],
            "duplicate_identity_conflicts": quality["duplicate_identity_conflicts"],
            "orphan_approval_count": quality["orphan_approval_count"],
        },
        top_actions=top_actions,
    )


@router.get("/cockpit/multi-org", response_model=MultiOrgCockpitRead)
async def multi_org_cockpit(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> MultiOrgCockpitRead:
    orgs = await organization_service.list_organizations(db)
    items: list[MultiOrgCockpitOrgRead] = []
    for org in orgs[:200]:
        clone_summary = await clone_brain.clone_org_summary(db, organization_id=org.id, week_start_date=None)
        compliance = await compliance_engine.latest_report(db, org.id)
        quality = await clone_control.data_quality_snapshot(db, organization_id=org.id)
        items.append(
            MultiOrgCockpitOrgRead(
                org_id=org.id,
                org_name=org.name,
                clone_summary=clone_summary,
                compliance_open_count=int(compliance.get("count", 0)),
                data_quality={
                    "missing_identity_count": quality["missing_identity_count"],
                    "stale_metrics_count": quality["stale_metrics_count"],
                },
            )
        )
    return MultiOrgCockpitRead(generated_at=datetime.now(timezone.utc), organizations=items)


@router.get("/founder-playbook/today", response_model=FounderPlaybookRead)
async def founder_playbook_today(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> FounderPlaybookRead:
    org_id = int(actor["org_id"])
    now = datetime.now(timezone.utc)
    compliance = await compliance_engine.latest_report(db, org_id)
    clone_summary = await clone_brain.clone_org_summary(db, organization_id=org_id, week_start_date=None)
    sla = await clone_control.manager_sla_snapshot(db, organization_id=org_id)
    data_quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)
    pending = await email_control.build_pending_actions_digest(db, org_id=org_id)

    open_violations = int(compliance.get("count", 0))
    avg_clone_score_raw = clone_summary.get("avg_score", 0.0)
    avg_clone_score = float(avg_clone_score_raw) if isinstance(avg_clone_score_raw, (int, float)) else 0.0
    missing_identity_raw = data_quality.get("missing_identity_count", 0)
    pending_breached_raw = sla.get("pending_approvals_breached", 0)
    missing_identity = int(missing_identity_raw) if isinstance(missing_identity_raw, int) else 0
    pending_breached = int(pending_breached_raw) if isinstance(pending_breached_raw, int) else 0
    total_open_tasks = int(pending.get("total_open_tasks", 0))

    today_focus = [
        f"Resolve top {min(open_violations, 5)} policy/compliance risks first.",
        f"Reduce open-task load from {total_open_tasks} with owner-level execution blocks.",
        f"Lift clone readiness above current average score {avg_clone_score:.1f}.",
    ]
    people_growth_actions = [
        "Run 15-minute coaching with each manager on blockers and delegation quality.",
        "Close identity gaps so every active employee has mapped work systems.",
        "Mark one weekly training plan DONE per employee before day-end.",
    ]
    strategic_growth_actions = [
        "Reallocate complex work to top readiness clones for faster delivery.",
        "Prioritize tasks with clear 30/90-day leverage and measurable outcomes.",
        "Convert pending high-impact decisions into approved execution plans.",
    ]
    evening_reflection = [
        "What actions increased trust and team capability today?",
        "Which decision created the highest growth leverage?",
        "What should be stopped tomorrow to protect focus?",
    ]
    coaching_prompts = [
        "Act as my Love + Growth strategist: protect people and increase capability.",
        "Convert today into: immediate action, growth action, strategic action.",
        "For each decision: Why now -> Owner -> KPI -> Risk -> Next checkpoint.",
    ]

    if missing_identity > 0:
        people_growth_actions.insert(0, f"Fix {missing_identity} unmapped employee identity records.")
    if pending_breached > 0:
        today_focus.insert(0, f"Clear {pending_breached} approval SLA breaches immediately.")

    return FounderPlaybookRead(
        generated_at=now,
        core_values=["Love", "Growth", "Strategic Execution"],
        north_star="Build people and systems that grow sustainably with trust.",
        today_focus=today_focus[:5],
        people_growth_actions=people_growth_actions[:5],
        strategic_growth_actions=strategic_growth_actions[:5],
        evening_reflection=evening_reflection,
        coaching_prompts=coaching_prompts,
    )


@router.get("/ceo/morning-brief", response_model=CEOMorningBriefRead)
async def ceo_morning_brief(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CEOMorningBriefRead:
    org_id = int(actor["org_id"])
    now = datetime.now(timezone.utc)
    ceo = await ceo_status(db=db, actor=actor)
    quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)
    sla = await clone_control.manager_sla_snapshot(db, organization_id=org_id)
    priority_actions: list[str] = []
    if sla.get("pending_approvals_breached", 0):
        priority_actions.append(f"Clear {sla['pending_approvals_breached']} approval SLA breaches.")
    if quality.get("missing_identity_count", 0):
        priority_actions.append(f"Resolve {quality['missing_identity_count']} missing identity mappings.")
    if ceo.branch_protection_issues:
        priority_actions.append(f"Fix branch protection gaps on {len(ceo.branch_protection_issues)} critical repos.")
    if ceo.infra_risks:
        priority_actions.append(f"Review {len(ceo.infra_risks)} infra backup risks in DigitalOcean.")
    if not priority_actions:
        priority_actions.append("No critical blockers detected. Focus on strategic execution plan.")
    return CEOMorningBriefRead(
        generated_at=now,
        priority_actions=priority_actions[:5],
        risk_snapshot={
            "overdue_critical_tasks": len(ceo.top_overdue_critical_tasks),
            "prs_waiting_sharon_review": len(ceo.prs_waiting_sharon_review),
            "branch_protection_issues": len(ceo.branch_protection_issues),
            "infra_risks": len(ceo.infra_risks),
            "cost_alerts": len(ceo.cost_alerts),
            "sla_status": sla.get("status", "unknown"),
        },
        mode="suggest_only",
    )
