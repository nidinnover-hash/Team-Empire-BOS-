from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.layers import (
    AISkillRoutingLayerReport,
    CloneMarketingSalesLayerReport,
    CloneTrainingLayerReport,
    EmployeeManagementLayerReport,
    EmployeePerformanceLayerReport,
    MarketingLayerReport,
    OpportunityAssociationLayerReport,
    RevenueManagementLayerReport,
    StaffProsperityLayerReport,
    StaffTrainingLayerReport,
    StudyLayerReport,
    TrainingLayerReport,
)
from app.schemas.data_collection import BrandingPowerReport, EthicalBoundaryReport, FraudLayerReport, MediaEditingLayerReport, SocialManagementLayerReport, ThreatLayerReport
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


@router.get("/employee-management", response_model=EmployeeManagementLayerReport)
async def employee_management_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmployeeManagementLayerReport:
    return await layers_service.get_employee_management_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/revenue-management", response_model=RevenueManagementLayerReport)
async def revenue_management_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> RevenueManagementLayerReport:
    return await layers_service.get_revenue_management_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/training-staff", response_model=StaffTrainingLayerReport)
async def training_staff_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> StaffTrainingLayerReport:
    return await layers_service.get_staff_training_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/ai-skill-routing", response_model=AISkillRoutingLayerReport)
async def ai_skill_routing_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> AISkillRoutingLayerReport:
    return await layers_service.get_ai_skill_routing_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/staff-prosperity", response_model=StaffProsperityLayerReport)
async def staff_prosperity_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> StaffProsperityLayerReport:
    return await layers_service.get_staff_prosperity_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/clone-training", response_model=CloneTrainingLayerReport)
async def clone_training_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CloneTrainingLayerReport:
    return await layers_service.get_clone_training_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/clone-marketing-sales", response_model=CloneMarketingSalesLayerReport)
async def clone_marketing_sales_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CloneMarketingSalesLayerReport:
    return await layers_service.get_clone_marketing_sales_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/opportunity-association", response_model=OpportunityAssociationLayerReport)
async def opportunity_association_layer(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> OpportunityAssociationLayerReport:
    return await layers_service.get_opportunity_association_layer(
        db=db,
        organization_id=int(actor["org_id"]),
        window_days=window_days,
    )


@router.get("/threat-detection", response_model=ThreatLayerReport)
async def threat_detection_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ThreatLayerReport:
    return await layers_service.get_threat_detection_layer(
        db=db,
        organization_id=int(actor["org_id"]),
    )


@router.get("/branding-power", response_model=BrandingPowerReport)
async def branding_power_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> BrandingPowerReport:
    return await layers_service.get_branding_power_layer(
        db=db,
        organization_id=int(actor["org_id"]),
    )


@router.get("/fraud-detection", response_model=FraudLayerReport)
async def fraud_detection_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> FraudLayerReport:
    return await layers_service.get_fraud_detection_layer(
        db=db,
        organization_id=int(actor["org_id"]),
    )


@router.get("/ethical-boundary", response_model=EthicalBoundaryReport)
async def ethical_boundary_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EthicalBoundaryReport:
    return await layers_service.get_ethical_boundary_layer(
        db=db,
        organization_id=int(actor["org_id"]),
    )


@router.get("/media-editing", response_model=MediaEditingLayerReport)
async def media_editing_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MediaEditingLayerReport:
    return await layers_service.get_media_editing_layer(
        db=db,
        organization_id=int(actor["org_id"]),
    )


@router.get("/social-management", response_model=SocialManagementLayerReport)
async def social_management_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SocialManagementLayerReport:
    return await layers_service.get_social_management_layer(
        db=db,
        organization_id=int(actor["org_id"]),
    )
