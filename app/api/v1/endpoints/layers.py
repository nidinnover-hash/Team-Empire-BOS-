from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.layers import (
    EmployeePerformanceLayerReport,
    MarketingLayerReport,
    StudyLayerReport,
    TrainingLayerReport,
)
from app.services import layers as layers_service

router = APIRouter(prefix="/layers", tags=["Layers"])


@router.get("/marketing", response_model=MarketingLayerReport)
async def marketing_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MarketingLayerReport:
    return await layers_service.get_marketing_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/study", response_model=StudyLayerReport)
async def study_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> StudyLayerReport:
    return await layers_service.get_study_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/training", response_model=TrainingLayerReport)
async def training_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> TrainingLayerReport:
    return await layers_service.get_training_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/employee-performance", response_model=EmployeePerformanceLayerReport)
async def employee_performance_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmployeePerformanceLayerReport:
    return await layers_service.get_employee_performance_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )
