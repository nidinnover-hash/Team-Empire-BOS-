from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._integration_helpers import (
    CONNECT_EXCEPTIONS,
    audit_connect_success,
    audit_sync,
    handle_connect_error,
)
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.integration import (
    HubSpotConnectRequest,
    HubSpotStatusRead,
    HubSpotSyncResult,
)
from app.services import hubspot_service

router = APIRouter(tags=["Integrations"])


@router.post("/hubspot/connect", response_model=HubSpotStatusRead, status_code=201)
async def hubspot_connect(
    data: HubSpotConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> HubSpotStatusRead:
    try:
        info = await hubspot_service.connect_hubspot(
            db, org_id=int(actor["org_id"]), access_token=data.access_token,
        )
    except CONNECT_EXCEPTIONS as exc:
        await handle_connect_error(db, integration_type="hubspot", actor=actor, exc=exc)
    await audit_connect_success(db, integration_type="hubspot", actor=actor, entity_id=info["id"])
    return HubSpotStatusRead(connected=True)


@router.get("/hubspot/status", response_model=HubSpotStatusRead)
async def hubspot_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> HubSpotStatusRead:
    status = await hubspot_service.get_hubspot_status(db, org_id=int(actor["org_id"]))
    return HubSpotStatusRead(**status)


@router.post("/hubspot/sync", response_model=HubSpotSyncResult)
async def hubspot_sync(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> HubSpotSyncResult:
    try:
        result = await hubspot_service.sync_hubspot_data(db, org_id=int(actor["org_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Sync failed. Check connection and try again.") from exc
    await audit_sync(
        db, event_type="hubspot_synced", actor=actor,
        payload={"contacts": result["contacts_synced"], "deals": result["deals_synced"]},
    )
    return HubSpotSyncResult(**result)
