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
    CalendlyConnectRequest,
    CalendlyStatusRead,
    CalendlySyncResult,
)
from app.services import calendly_service

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
    except CONNECT_EXCEPTIONS as exc:
        await handle_connect_error(db, integration_type="calendly", actor=actor, exc=exc)
    await audit_connect_success(db, integration_type="calendly", actor=actor, entity_id=info["id"])
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, RuntimeError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Calendly sync failed due to upstream error. Retry shortly.") from exc
    normalized = normalize_sync_result(
        result,
        integration_type="calendly",
        required_int_fields=("events_synced", "upcoming_events"),
    )
    await audit_sync(
        db,
        event_type="calendly_synced",
        actor=actor,
        payload={"events_synced": normalized["events_synced"]},
    )
    return CalendlySyncResult(
        events_synced=normalized["events_synced"],
        upcoming_events=normalized["upcoming_events"],
        last_sync_at=result.get("last_sync_at"),
    )
