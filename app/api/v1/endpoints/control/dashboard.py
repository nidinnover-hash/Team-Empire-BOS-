"""Unified control dashboard — pending approvals, recent placements, money approvals, SLA/risk."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_control_scope_org_ids, get_db
from app.core.rbac import require_roles
from app.models.approval import Approval
from app.models.organization import Organization
from app.models.recruitment_placement import RecruitmentPlacement
from app.models.study_abroad import StudyAbroadApplication, StudyAbroadApplicationStep

router = APIRouter(prefix="/dashboard", tags=["Control Dashboard"])


class SectorKpi(BaseModel):
    org_id: int
    slug: str
    industry_type: str | None
    pending_approvals_count: int
    study_abroad_at_risk_count: int
    placements_count_7d: int
    money_approvals_count_7d: int


class ControlDashboardResponse(BaseModel):
    pending_approvals_count: int
    pending_approvals_recent: list[dict]
    recent_placements: list[dict]
    recent_money_approvals: list[dict]
    study_abroad_at_risk_count: int
    generated_at: str
    scope_org_ids: list[int] = []
    sector_kpis: list[SectorKpi] = []


async def _control_summary_single_org(
    db: AsyncSession,
    org_id: int,
    now: datetime,
    cutoff_7d: datetime,
) -> tuple[int, list[dict], list[dict], list[dict], int]:
    """Return (pending_count, recent_pending, recent_placements, recent_money, at_risk_count)."""
    pending_count_result = await db.execute(
        select(func.count(Approval.id)).where(
            Approval.organization_id == org_id,
            Approval.status == "pending",
        )
    )
    pending_count = int(pending_count_result.scalar() or 0)

    recent_pending_result = await db.execute(
        select(Approval)
        .where(
            Approval.organization_id == org_id,
            Approval.status == "pending",
        )
        .order_by(Approval.created_at.desc())
        .limit(10)
    )
    recent_pending = [
        {"id": a.id, "approval_type": a.approval_type, "created_at": a.created_at.isoformat() if a.created_at else None, "organization_id": org_id}
        for a in recent_pending_result.scalars().all()
    ]

    placements_result = await db.execute(
        select(RecruitmentPlacement)
        .where(
            RecruitmentPlacement.organization_id == org_id,
            RecruitmentPlacement.created_at >= cutoff_7d,
        )
        .order_by(RecruitmentPlacement.created_at.desc())
        .limit(10)
    )
    recent_placements = [
        {
            "id": p.id,
            "candidate_id": p.candidate_id,
            "job_id": p.job_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "organization_id": org_id,
        }
        for p in placements_result.scalars().all()
    ]

    money_result = await db.execute(
        select(Approval)
        .where(
            Approval.organization_id == org_id,
            Approval.approval_type.like("money_%"),
            Approval.created_at >= cutoff_7d,
        )
        .order_by(Approval.created_at.desc())
        .limit(10)
    )
    recent_money = [
        {
            "id": a.id,
            "approval_type": a.approval_type,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "organization_id": org_id,
        }
        for a in money_result.scalars().all()
    ]

    at_risk_result = await db.execute(
        select(func.count(StudyAbroadApplicationStep.id))
        .select_from(StudyAbroadApplicationStep)
        .join(StudyAbroadApplication, StudyAbroadApplication.id == StudyAbroadApplicationStep.application_id)
        .where(
            StudyAbroadApplication.organization_id == org_id,
            StudyAbroadApplicationStep.deadline.isnot(None),
            StudyAbroadApplicationStep.deadline < now,
            StudyAbroadApplicationStep.completed_at.is_(None),
        )
    )
    at_risk = int(at_risk_result.scalar() or 0)

    placements_count_7d_result = await db.execute(
        select(func.count(RecruitmentPlacement.id)).where(
            RecruitmentPlacement.organization_id == org_id,
            RecruitmentPlacement.created_at >= cutoff_7d,
        )
    )
    money_count_7d_result = await db.execute(
        select(func.count(Approval.id)).where(
            Approval.organization_id == org_id,
            Approval.approval_type.like("money_%"),
            Approval.created_at >= cutoff_7d,
        )
    )
    placements_count_7d = int(placements_count_7d_result.scalar() or 0)
    money_count_7d = int(money_count_7d_result.scalar() or 0)

    return pending_count, recent_pending, recent_placements, recent_money, at_risk, placements_count_7d, money_count_7d


@router.get("/control-summary", response_model=ControlDashboardResponse)
async def control_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    org_ids: list[int] = Depends(get_control_scope_org_ids),
) -> ControlDashboardResponse:
    """
    Single or cross-org view: pending approvals, recent placements, money approvals,
    study-abroad at-risk. Use X-BOS-Company: all (CEO only) or empireo | esa | empire-digital | codnov.
    """
    now = datetime.now(UTC)
    cutoff_7d = now - timedelta(days=7)

    if not org_ids:
        org_ids = [int(actor["org_id"])]

    if len(org_ids) == 1:
        org_id = org_ids[0]
        (
            pending_approvals_count,
            pending_approvals_recent,
            recent_placements,
            recent_money_approvals,
            study_abroad_at_risk_count,
            _,
            _,
        ) = await _control_summary_single_org(db, org_id, now, cutoff_7d)
        # Drop organization_id from items for single-org to keep response shape backward compatible
        for a in pending_approvals_recent:
            a.pop("organization_id", None)
        for p in recent_placements:
            p.pop("organization_id", None)
        for a in recent_money_approvals:
            a.pop("organization_id", None)
        return ControlDashboardResponse(
            pending_approvals_count=pending_approvals_count,
            pending_approvals_recent=pending_approvals_recent,
            recent_placements=recent_placements,
            recent_money_approvals=recent_money_approvals,
            study_abroad_at_risk_count=study_abroad_at_risk_count,
            generated_at=now.isoformat(),
            scope_org_ids=org_ids,
            sector_kpis=[],
        )

    # Cross-org (CEO "All Companies"): aggregate and add sector KPIs
    total_pending = 0
    total_at_risk = 0
    all_recent_pending: list[dict] = []
    all_recent_placements: list[dict] = []
    all_recent_money: list[dict] = []
    sector_kpis: list[SectorKpi] = []

    org_id_to_slug: dict[int, tuple[str, str | None]] = {}
    org_result = await db.execute(
        select(Organization).where(Organization.id.in_(org_ids))
    )
    for o in org_result.scalars().all():
        org_id_to_slug[int(o.id)] = (o.slug, o.industry_type)

    for org_id in org_ids:
        (
            p_count,
            r_pending,
            r_placements,
            r_money,
            at_risk,
            placements_7d,
            money_7d,
        ) = await _control_summary_single_org(db, org_id, now, cutoff_7d)
        total_pending += p_count
        total_at_risk += at_risk
        all_recent_pending.extend(r_pending)
        all_recent_placements.extend(r_placements)
        all_recent_money.extend(r_money)
        slug, industry_type = org_id_to_slug.get(org_id, (str(org_id), None))
        sector_kpis.append(
            SectorKpi(
                org_id=org_id,
                slug=slug,
                industry_type=industry_type,
                pending_approvals_count=p_count,
                study_abroad_at_risk_count=at_risk,
                placements_count_7d=placements_7d,
                money_approvals_count_7d=money_7d,
            )
        )

    all_recent_pending.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
    all_recent_placements.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
    all_recent_money.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
    pending_approvals_recent = all_recent_pending[:10]
    recent_placements = all_recent_placements[:10]
    recent_money_approvals = all_recent_money[:10]

    return ControlDashboardResponse(
        pending_approvals_count=total_pending,
        pending_approvals_recent=pending_approvals_recent,
        recent_placements=recent_placements,
        recent_money_approvals=recent_money_approvals,
        study_abroad_at_risk_count=total_at_risk,
        generated_at=now.isoformat(),
        scope_org_ids=org_ids,
        sector_kpis=sector_kpis,
    )
