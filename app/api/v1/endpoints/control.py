from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
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
    CEOStatusRead,
    ComplianceReportRead,
    ComplianceRunRead,
    GitHubIdentityMapListRead,
    GitHubIdentityMapUpsertRead,
    GitHubIdentityMapUpsertRequest,
    HealthSummaryRead,
    IntegrationHealthRead,
    MessageDraftRead,
    MessageDraftRequest,
    SchedulerJobRunListRead,
    SchedulerReplayRead,
    SchedulerReplayRequest,
)
from app.services import compliance_engine
from app.services import sync_scheduler

router = APIRouter(prefix="/control", tags=["CEO Control"])


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
    cutoff = now.timestamp() - (settings.SYNC_STALE_HOURS * 3600)
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
        items.append(
            {
                "type": row.type,
                "connected": row.status == "connected",
                "last_sync_status": row.last_sync_status,
                "last_sync_at": row.last_sync_at,
                "stale": stale,
                "age_hours": age_hours,
            }
        )
    return IntegrationHealthRead(
        generated_at=now,
        stale_hours_threshold=int(settings.SYNC_STALE_HOURS),
        total_connected=len(items),
        failing_count=sum(1 for x in items if x.get("last_sync_status") == "error"),
        stale_count=sum(1 for x in items if x.get("stale")),
        items=items,
    )


@router.post("/compliance/run", response_model=ComplianceRunRead)
async def compliance_run(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ComplianceRunRead:
    org_id = int(actor["org_id"])
    result = await compliance_engine.run_compliance(db, org_id)
    return ComplianceRunRead(ok=True, compliance_score=int(result["compliance_score"]), violations=result["violations"], mode="suggest_only")


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
    items = [
        {
            "id": row.id,
            "job_name": row.job_name,
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "duration_ms": row.duration_ms,
            "details": json.loads(row.details_json or "{}"),
            "error": row.error,
        }
        for row in rows
    ]
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
