from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.core.request_context import get_current_request_id
from app.logs.audit import record_action
from app.schemas.integration import (
    DigitalOceanConnectRequest,
    DigitalOceanStatusRead,
    DigitalOceanSyncResult,
)
from app.services import do_service

router = APIRouter(tags=["Integrations"])


@router.post("/digitalocean/connect", response_model=DigitalOceanStatusRead, status_code=201)
async def digitalocean_connect(
    data: DigitalOceanConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DigitalOceanStatusRead:
    request_id = get_current_request_id()
    try:
        await do_service.connect_digitalocean(db, org_id=int(actor["org_id"]), api_token=data.api_token)
    except (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        await record_action(
            db,
            event_type="integration_connected",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={
                "type": "digitalocean",
                "request_id": request_id,
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="DigitalOcean connection failed. Check your API token.",
        ) from exc
    status = await do_service.get_digitalocean_status(db, org_id=int(actor["org_id"]))
    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={"type": "digitalocean", "request_id": request_id, "status": "ok"},
    )
    return DigitalOceanStatusRead(**status)


@router.get("/digitalocean/status", response_model=DigitalOceanStatusRead)
async def digitalocean_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DigitalOceanStatusRead:
    status = await do_service.get_digitalocean_status(db, org_id=int(actor["org_id"]))
    return DigitalOceanStatusRead(**status)


@router.post("/digitalocean/sync", response_model=DigitalOceanSyncResult)
async def digitalocean_sync(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DigitalOceanSyncResult:
    request_id = get_current_request_id()
    result = await do_service.sync_digitalocean(db, org_id=int(actor["org_id"]))
    if result.get("error"):
        await record_action(
            db,
            event_type="digitalocean_synced",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={"request_id": request_id, "status": "error", "error": result.get("error")},
        )
        raise HTTPException(status_code=400, detail="DigitalOcean sync failed. Check your configuration.")
    await record_action(
        db,
        event_type="digitalocean_synced",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={
            "request_id": request_id,
            "status": "ok",
            "droplets_synced": result.get("droplets_synced", 0),
            "team_members_synced": result.get("team_members_synced", 0),
        },
    )
    return DigitalOceanSyncResult(**result)
