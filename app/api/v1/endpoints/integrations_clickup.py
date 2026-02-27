
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._integration_helpers import normalize_sync_result
from app.core.deps import get_db
from app.core.idempotency import (
    IdempotencyConflictError,
    build_fingerprint,
    get_cached_response,
    store_response,
)
from app.core.rbac import require_roles
from app.core.request_context import get_current_request_id
from app.logs.audit import record_action
from app.schemas.integration import ClickUpConnectRequest, ClickUpStatusRead, ClickUpSyncResult
from app.services import clickup_service

router = APIRouter(tags=["Integrations"])


@router.post("/clickup/connect", response_model=ClickUpStatusRead, status_code=201)
async def clickup_connect(
    data: ClickUpConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ClickUpStatusRead:
    """
    Verify a ClickUp personal API token and store it encrypted in the Integration table.
    Get your token at: https://app.clickup.com/settings/apps (Personal API Token section).
    """
    request_id = get_current_request_id()
    try:
        info = await clickup_service.connect_clickup(
            db, org_id=int(actor["org_id"]), api_token=data.api_token
        )
    except (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        await record_action(
            db,
            event_type="integration_connected",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={
                "type": "clickup",
                "request_id": request_id,
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="ClickUp connection failed. Check your API token.",
        ) from exc

    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=info["id"],
        payload_json={"type": "clickup", "username": info.get("username"), "request_id": request_id, "status": "ok"},
    )
    return ClickUpStatusRead(
        connected=True,
        last_sync_at=None,
        username=info.get("username"),
        team_id=info.get("team_id"),
    )


@router.get("/clickup/status", response_model=ClickUpStatusRead)
async def clickup_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ClickUpStatusRead:
    status = await clickup_service.get_clickup_status(db, org_id=int(actor["org_id"]))
    return ClickUpStatusRead(**status)


@router.post("/clickup/sync", response_model=ClickUpSyncResult)
async def clickup_sync(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ClickUpSyncResult:
    request_id = get_current_request_id()
    scope = f"clickup_sync:{actor['org_id']}"
    fingerprint = build_fingerprint({"org_id": int(actor["org_id"]), "action": "clickup_sync"})
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return ClickUpSyncResult.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict: this key was already used with a different request body") from exc
    try:
        result = await clickup_service.sync_clickup_tasks(db, org_id=int(actor["org_id"]))
    except (RuntimeError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        raise HTTPException(status_code=502, detail="ClickUp sync failed due to upstream error. Retry shortly.") from exc
    normalized = normalize_sync_result(
        result,
        integration_type="clickup",
        required_int_fields=("synced",),
    )
    if normalized["error"]:
        await record_action(
            db,
            event_type="clickup_synced",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={"request_id": request_id, "status": "error", "error": normalized["error"]},
        )
        raise HTTPException(status_code=400, detail=normalized["error"])

    await record_action(
        db,
        event_type="clickup_synced",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={"request_id": request_id, "status": "ok", "synced": normalized["synced"]},
    )

    status = await clickup_service.get_clickup_status(db, org_id=int(actor["org_id"]))
    response = ClickUpSyncResult(
        synced=normalized["synced"],
        last_sync_at=status.get("last_sync_at"),
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response
