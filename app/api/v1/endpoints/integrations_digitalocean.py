from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
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
    await do_service.connect_digitalocean(db, org_id=int(actor["org_id"]), api_token=data.api_token)
    status = await do_service.get_digitalocean_status(db, org_id=int(actor["org_id"]))
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
    result = await do_service.sync_digitalocean(db, org_id=int(actor["org_id"]))
    return DigitalOceanSyncResult(**result)
