from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    GoogleAnalyticsConnectRequest,
    GoogleAnalyticsStatusRead,
    GoogleAnalyticsSyncResult,
)
from app.services import google_analytics_service

router = APIRouter(tags=["Integrations"])


@router.post("/google-analytics/connect", response_model=GoogleAnalyticsStatusRead, status_code=201)
async def ga_connect(
    data: GoogleAnalyticsConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GoogleAnalyticsStatusRead:
    try:
        result = await google_analytics_service.connect_google_analytics(
            db,
            org_id=int(actor["org_id"]),
            access_token=data.access_token,
            property_id=data.property_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Google Analytics connection failed ({type(exc).__name__}). Check token and GA4 property ID.",
        ) from exc
    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=int(result["id"]),
        payload_json={"type": "google_analytics", "status": "connected", "property_id": result["property_id"]},
    )
    return GoogleAnalyticsStatusRead(connected=True, property_id=str(result["property_id"]))


@router.get("/google-analytics/status", response_model=GoogleAnalyticsStatusRead)
async def ga_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GoogleAnalyticsStatusRead:
    status = await google_analytics_service.get_ga_status(db, org_id=int(actor["org_id"]))
    return GoogleAnalyticsStatusRead(**status)


@router.post("/google-analytics/sync", response_model=GoogleAnalyticsSyncResult)
async def ga_sync(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GoogleAnalyticsSyncResult:
    try:
        result = await google_analytics_service.sync_analytics(db, org_id=int(actor["org_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_action(
        db, event_type="ga_synced", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=None, payload_json={"sessions": result["sessions_30d"]},
    )
    return GoogleAnalyticsSyncResult(**result)
