"""Deal pipeline forecasting endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import deal_forecast as forecast_service

router = APIRouter(prefix="/deals/forecast", tags=["Deal Forecasting"])


@router.get("/pipeline")
async def pipeline_forecast(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Weighted pipeline forecast broken down by stage."""
    return await forecast_service.get_pipeline_forecast(db, organization_id=actor["org_id"])


@router.get("/win-rates")
async def win_rate_trends(
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Win rate trends by month."""
    return await forecast_service.get_win_rate_trends(db, organization_id=actor["org_id"], months=months)
