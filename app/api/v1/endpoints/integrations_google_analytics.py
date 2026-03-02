import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._integration_helpers import (
    CONNECT_EXCEPTIONS,
    audit_connect_success,
    audit_sync,
    handle_connect_error,
    normalize_sync_result,
)
from app.core.deps import get_db
from app.core.rbac import require_roles
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
    except CONNECT_EXCEPTIONS as exc:
        await handle_connect_error(db, integration_type="google_analytics", actor=actor, exc=exc)
    await audit_connect_success(
        db, integration_type="google_analytics", actor=actor, entity_id=int(result["id"]),
        extra={"property_id": result["property_id"]},
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
        raise HTTPException(status_code=400, detail="Google Analytics sync configuration error") from exc
    except (httpx.HTTPError, RuntimeError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Google Analytics sync failed due to upstream error. Retry shortly.") from exc
    normalized = normalize_sync_result(
        result,
        integration_type="google analytics",
        required_int_fields=("sessions_30d", "active_users_30d", "page_views_30d"),
    )
    top_pages = result.get("top_pages")
    traffic_sources = result.get("traffic_sources")
    if not isinstance(top_pages, list) or not isinstance(traffic_sources, list):
        raise HTTPException(status_code=502, detail="Google Analytics sync returned invalid response shape.")
    await audit_sync(db, event_type="ga_synced", actor=actor, payload={"sessions": normalized["sessions_30d"]})
    return GoogleAnalyticsSyncResult(
        sessions_30d=normalized["sessions_30d"],
        active_users_30d=normalized["active_users_30d"],
        page_views_30d=normalized["page_views_30d"],
        top_pages=top_pages,
        traffic_sources=traffic_sources,
    )
