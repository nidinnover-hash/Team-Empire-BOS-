import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    HubSpotConnectRequest,
    HubSpotStatusRead,
    HubSpotSyncResult,
)
from app.services import hubspot_service

logger = logging.getLogger(__name__)

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
    except (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        logger.warning("request failed: %s", exc)
        raise HTTPException(status_code=400, detail="Connection failed. Check credentials and try again.") from exc
    await record_action(
        db, event_type="integration_connected", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=info["id"], payload_json={"type": "hubspot", "status": "ok"},
    )
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
        logger.warning("request failed: %s", exc)
        raise HTTPException(status_code=400, detail="Connection failed. Check credentials and try again.") from exc
    await record_action(
        db, event_type="hubspot_synced", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=None, payload_json={"contacts": result["contacts_synced"], "deals": result["deals_synced"]},
    )
    return HubSpotSyncResult(**result)
