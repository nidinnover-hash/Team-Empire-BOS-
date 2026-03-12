"""Per-org scorecards (ESA, EmpireO, Codnov) — Q1 targets and bands."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.recruitment_placement import RecruitmentPlacement
from app.models.study_abroad import StudyAbroadApplication, StudyAbroadApplicationStep
from app.schemas.empire_digital import ScorecardRead, ScorecardTile

# Q1 targets: ESA applications 100/mo, enrolments 50, at_risk ≤10
SCORECARD_ESA = {
    "applications": {"target": 100, "green_min": 100, "amber_min": 70},
    "at_risk": {"target": 0, "green_max": 10, "amber_max": 25},
}
# EmpireO: placements 20/mo
SCORECARD_EMPIREO = {
    "placements": {"target": 20, "green_min": 20, "amber_min": 14},
}
# Codnov: projects 10/mo, on_time 85%
SCORECARD_CODNOV = {
    "projects_started": {"target": 10, "green_min": 10, "amber_min": 7},
    "on_time_pct": {"target": 85.0, "green_min": 85.0, "amber_min": 70.0},
}


def _band_higher_better(value: int | float, green_min: int | float, amber_min: int | float) -> str:
    if value >= green_min:
        return "green"
    if value >= amber_min:
        return "amber"
    return "red"


def _band_lower_better(value: int | float, green_max: int | float, amber_max: int | float) -> str:
    if value <= green_max:
        return "green"
    if value <= amber_max:
        return "amber"
    return "red"


async def get_scorecard_esa(
    db: AsyncSession,
    *,
    organization_id: int,
    window_days: int = 30,
) -> ScorecardRead:
    """ESA scorecard: applications (lead→application), at-risk count."""
    window_days = max(1, min(31, int(window_days)))
    now = datetime.now(UTC)
    window_start = now - timedelta(days=window_days)

    app_result = await db.execute(
        select(func.count(StudyAbroadApplication.id)).where(
            StudyAbroadApplication.organization_id == organization_id,
            StudyAbroadApplication.created_at >= window_start,
        )
    )
    applications = int(app_result.scalar() or 0)

    at_risk_result = await db.execute(
        select(func.count(StudyAbroadApplicationStep.id))
        .select_from(StudyAbroadApplicationStep)
        .join(StudyAbroadApplication, StudyAbroadApplication.id == StudyAbroadApplicationStep.application_id)
        .where(
            StudyAbroadApplication.organization_id == organization_id,
            StudyAbroadApplicationStep.deadline.isnot(None),
            StudyAbroadApplicationStep.deadline < now,
            StudyAbroadApplicationStep.completed_at.is_(None),
        )
    )
    at_risk = int(at_risk_result.scalar() or 0)

    cfg_app = SCORECARD_ESA["applications"]
    cfg_risk = SCORECARD_ESA["at_risk"]
    tiles = [
        ScorecardTile(
            key="applications",
            label=f"Applications ({window_days}d)",
            value=applications,
            band=_band_higher_better(applications, cfg_app["green_min"], cfg_app["amber_min"]),
            target=cfg_app["target"],
        ),
        ScorecardTile(
            key="at_risk",
            label="At-risk (overdue steps)",
            value=at_risk,
            band=_band_lower_better(at_risk, cfg_risk["green_max"], cfg_risk["amber_max"]),
            target=0,
        ),
    ]
    return ScorecardRead(window_days=window_days, tiles=tiles)


async def get_scorecard_empireo(
    db: AsyncSession,
    *,
    organization_id: int,
    window_days: int = 30,
) -> ScorecardRead:
    """EmpireO scorecard: placements this month."""
    window_days = max(1, min(31, int(window_days)))
    now = datetime.now(UTC)
    window_start = now - timedelta(days=window_days)

    result = await db.execute(
        select(func.count(RecruitmentPlacement.id)).where(
            RecruitmentPlacement.organization_id == organization_id,
            RecruitmentPlacement.created_at >= window_start,
        )
    )
    placements = int(result.scalar() or 0)
    cfg = SCORECARD_EMPIREO["placements"]
    tiles = [
        ScorecardTile(
            key="placements",
            label=f"Placements ({window_days}d)",
            value=placements,
            band=_band_higher_better(placements, cfg["green_min"], cfg["amber_min"]),
            target=cfg["target"],
        ),
    ]
    return ScorecardRead(window_days=window_days, tiles=tiles)


async def get_scorecard_codnov(
    db: AsyncSession,
    *,
    organization_id: int,
    window_days: int = 30,
) -> ScorecardRead:
    """Codnov scorecard: projects started, on-time %."""
    window_days = max(1, min(31, int(window_days)))
    now = datetime.now(UTC)
    window_start = now - timedelta(days=window_days)

    started_result = await db.execute(
        select(func.count(Project.id)).where(
            Project.organization_id == organization_id,
            Project.created_at >= window_start,
            Project.is_deleted.is_(False),
        )
    )
    projects_started = int(started_result.scalar() or 0)

    completed_with_due = await db.execute(
        select(Project).where(
            Project.organization_id == organization_id,
            Project.status == "completed",
            Project.due_date.isnot(None),
            Project.is_deleted.is_(False),
        )
    )
    completed = list(completed_with_due.scalars().all())
    on_time = sum(1 for p in completed if p.updated_at and p.due_date and p.updated_at.date() <= p.due_date)
    total_with_due = len(completed)
    on_time_pct = (on_time / total_with_due * 100.0) if total_with_due else 100.0

    cfg_start = SCORECARD_CODNOV["projects_started"]
    cfg_ot = SCORECARD_CODNOV["on_time_pct"]
    tiles = [
        ScorecardTile(
            key="projects_started",
            label=f"Projects started ({window_days}d)",
            value=projects_started,
            band=_band_higher_better(projects_started, cfg_start["green_min"], cfg_start["amber_min"]),
            target=cfg_start["target"],
        ),
        ScorecardTile(
            key="on_time_pct",
            label="On-time delivery %",
            value=round(on_time_pct, 1),
            band=_band_higher_better(on_time_pct, cfg_ot["green_min"], cfg_ot["amber_min"]),
            target=cfg_ot["target"],
        ),
    ]
    return ScorecardRead(window_days=window_days, tiles=tiles)
