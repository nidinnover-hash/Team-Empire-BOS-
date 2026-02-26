import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    CalendlyConnectRequest,
    CalendlyStatusRead,
    CalendlySyncResult,
)
from app.services import calendly_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Integrations"])


@router.post("/calendly/connect", response_model=CalendlyStatusRead, status_code=201)
async def calendly_connect(
    data: CalendlyConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CalendlyStatusRead:
    try:
        info = await calendly_service.connect_calendly(
            db, org_id=int(actor["org_id"]), api_token=data.api_token,
        )
    except (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        logger.warning("request failed: %s", exc)
        raise HTTPException(status_code=400, detail="Connection failed. Check credentials and try again.") from exc
    await record_action(
        db, event_type="integration_connected", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=info["id"], payload_json={"type": "calendly", "status": "ok"},
    )
    return CalendlyStatusRead(connected=True, user_name=info.get("user_name"))


@router.get("/calendly/status", response_model=CalendlyStatusRead)
async def calendly_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CalendlyStatusRead:
    status = await calendly_service.get_calendly_status(db, org_id=int(actor["org_id"]))
    return CalendlyStatusRead(**status)


@router.post("/calendly/sync", response_model=CalendlySyncResult)
async def calendly_sync(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CalendlySyncResult:
    try:
        result = await calendly_service.sync_events(db, org_id=int(actor["org_id"]))
    except ValueError as exc:
        logger.warning("request failed: %s", exc)
        raise HTTPException(status_code=400, detail="Connection failed. Check credentials and try again.") from exc
    await record_action(
        db, event_type="calendly_synced", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=None, payload_json={"events_synced": result["events_synced"]},
    )
    return CalendlySyncResult(**result)
