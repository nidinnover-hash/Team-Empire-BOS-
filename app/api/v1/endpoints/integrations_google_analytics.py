from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    GoogleAnalyticsStatusRead,
    GoogleAnalyticsSyncResult,
)
from app.services import google_analytics_service

router = APIRouter(tags=["Integrations"])


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
