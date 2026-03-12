"""Unified scorecard API — returns org-specific scorecard by industry_type (Q1 targets)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.empire_digital import ScorecardRead
from app.services import empire_digital as empire_digital_service
from app.services import organization as organization_service
from app.services import scorecard as scorecard_service

router = APIRouter(prefix="/scorecard", tags=["Scorecard"])


@router.get("", response_model=ScorecardRead)
async def get_scorecard(
    window_days: int = Query(7, ge=1, le=31),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ScorecardRead:
    """
    Scorecard for current org. Dispatches by organization.industry_type:
    marketing -> Empire Digital, study_abroad -> ESA, recruitment -> EmpireO, tech -> Codnov.
    """
    org_id = int(actor["org_id"])
    org = await organization_service.get_organization_by_id(db, org_id)
    industry = (org.industry_type or "").strip().lower() if org else ""

    if industry == "marketing":
        return await empire_digital_service.get_scorecard_empire_digital(
            db,
            actor_org_id=org_id,
            actor_role=str(actor.get("role", "")).upper(),
            window_days=window_days,
        )
    if industry == "study_abroad":
        return await scorecard_service.get_scorecard_esa(
            db,
            organization_id=org_id,
            window_days=window_days,
        )
    if industry == "recruitment":
        return await scorecard_service.get_scorecard_empireo(
            db,
            organization_id=org_id,
            window_days=window_days,
        )
    if industry == "tech":
        return await scorecard_service.get_scorecard_codnov(
            db,
            organization_id=org_id,
            window_days=window_days,
        )
    return ScorecardRead(window_days=window_days, tiles=[])
