"""Intelligence layers — thin proxies to data_collection service functions."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_collection import (
    BrandingPowerReport,
    EthicalBoundaryReport,
    FraudLayerReport,
    MediaEditingLayerReport,
    SocialManagementLayerReport,
    ThreatLayerReport,
)


async def get_threat_detection_layer(
    db: AsyncSession,
    organization_id: int,
) -> ThreatLayerReport:
    from app.services.data_collection import get_threat_layer_report
    return await get_threat_layer_report(db, organization_id)


async def get_branding_power_layer(
    db: AsyncSession,
    organization_id: int,
) -> BrandingPowerReport:
    from app.services.data_collection import get_branding_power_report
    return await get_branding_power_report(db, organization_id)


async def get_fraud_detection_layer(
    db: AsyncSession,
    organization_id: int,
) -> FraudLayerReport:
    from app.services.data_collection import get_fraud_layer_report
    return await get_fraud_layer_report(db, organization_id)


async def get_ethical_boundary_layer(
    db: AsyncSession,
    organization_id: int,
) -> EthicalBoundaryReport:
    from app.services.data_collection import get_ethical_boundary_report
    return await get_ethical_boundary_report(db, organization_id)


async def get_media_editing_layer(
    db: AsyncSession,
    organization_id: int,
) -> MediaEditingLayerReport:
    from app.services.data_collection import get_media_editing_layer as _get
    return await _get(db, organization_id)


async def get_social_management_layer(
    db: AsyncSession,
    organization_id: int,
) -> SocialManagementLayerReport:
    from app.services.data_collection import get_social_management_layer as _get
    return await _get(db, organization_id)
