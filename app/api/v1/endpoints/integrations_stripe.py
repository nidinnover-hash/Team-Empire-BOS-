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
    StripeConnectRequest,
    StripeStatusRead,
    StripeSyncResult,
)
from app.services import stripe_service

router = APIRouter(tags=["Integrations"])


@router.post("/stripe/connect", response_model=StripeStatusRead, status_code=201)
async def stripe_connect(
    data: StripeConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> StripeStatusRead:
    try:
        info = await stripe_service.connect_stripe(
            db, org_id=int(actor["org_id"]), secret_key=data.secret_key,
        )
    except CONNECT_EXCEPTIONS as exc:
        await handle_connect_error(db, integration_type="stripe", actor=actor, exc=exc)
    await audit_connect_success(db, integration_type="stripe", actor=actor, entity_id=info["id"])
    return StripeStatusRead(connected=True)


@router.get("/stripe/status", response_model=StripeStatusRead)
async def stripe_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> StripeStatusRead:
    status = await stripe_service.get_stripe_status(db, org_id=int(actor["org_id"]))
    return StripeStatusRead(**status)


@router.post("/stripe/sync", response_model=StripeSyncResult)
async def stripe_sync(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> StripeSyncResult:
    try:
        result = await stripe_service.sync_stripe_data(db, org_id=int(actor["org_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Sync failed. Check connection and try again.") from exc
    await audit_sync(db, event_type="stripe_synced", actor=actor, payload={"charges": result["charges_synced"]})
    return StripeSyncResult(**result)
