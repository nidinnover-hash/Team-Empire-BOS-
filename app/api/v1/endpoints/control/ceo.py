"""CEO status, morning brief, board packet, founder playbook, and multi-org cockpit."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.ceo_control import (
    ClickUpTaskSnapshot,
    DigitalOceanCostSnapshot,
    DigitalOceanDropletSnapshot,
    GitHubPRSnapshot,
    GitHubRepoSnapshot,
)
from app.schemas.control import (
    CEOMorningBriefRead,
    CEOStatusRead,
    FounderPlaybookRead,
    MultiOrgCockpitOrgRead,
    MultiOrgCockpitRead,
    WeeklyBoardPacketRead,
)
from app.services import (
    clone_brain,
    clone_control,
    compliance_engine,
    email_control,
)
from app.services import organization as organization_service

router = APIRouter()


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


async def _fetch_ceo_status_data(db: AsyncSession, org_id: int) -> CEOStatusRead:
    """Shared data-fetching logic for CEO status -- used by both ceo_status and ceo_morning_brief."""
    tasks = (
        await db.execute(
            select(ClickUpTaskSnapshot)
            .where(ClickUpTaskSnapshot.organization_id == org_id)
            .order_by(ClickUpTaskSnapshot.synced_at.desc())
            .limit(200)
        )
    ).scalars().all()
    overdue = []
    now = datetime.now(UTC)
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


@router.get("/ceo/status", response_model=CEOStatusRead)
async def ceo_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CEOStatusRead:
    return await _fetch_ceo_status_data(db, int(actor["org_id"]))


@router.get("/weekly-board-packet", response_model=WeeklyBoardPacketRead)
async def weekly_board_packet(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WeeklyBoardPacketRead:
    org_id = int(actor["org_id"])
    now = datetime.now(UTC)
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
    org = await organization_service.get_organization_by_id(db, int(actor["org_id"]))
    orgs = [org] if org else []
    items: list[MultiOrgCockpitOrgRead] = []
    for org in orgs:
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
    return MultiOrgCockpitRead(generated_at=datetime.now(UTC), organizations=items)


@router.get("/founder-playbook/today", response_model=FounderPlaybookRead)
async def founder_playbook_today(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> FounderPlaybookRead:
    org_id = int(actor["org_id"])
    now = datetime.now(UTC)
    compliance = await compliance_engine.latest_report(db, org_id)
    clone_summary = await clone_brain.clone_org_summary(db, organization_id=org_id, week_start_date=None)
    sla = await clone_control.manager_sla_snapshot(db, organization_id=org_id)
    data_quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)
    pending = await email_control.build_pending_actions_digest(db, org_id=org_id)

    open_violations = int(compliance.get("count", 0))
    avg_clone_score_raw = clone_summary.get("avg_score", 0.0)
    avg_clone_score = float(avg_clone_score_raw) if isinstance(avg_clone_score_raw, int | float) else 0.0
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
    now = datetime.now(UTC)
    ceo = await _fetch_ceo_status_data(db, org_id)
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
