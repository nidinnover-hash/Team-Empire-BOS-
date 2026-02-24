from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.schemas.integration import (
    SlackConnectRequest,
    SlackSendRequest,
    SlackStatusRead,
    SlackSyncResult,
)
from app.services import slack_service

router = APIRouter(tags=["Integrations"])


@router.post("/slack/connect", response_model=SlackStatusRead, status_code=201)
async def slack_connect(
    data: SlackConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SlackStatusRead:
    request_id = get_current_request_id()
    try:
        info = await slack_service.connect_slack(
            db, org_id=int(actor["org_id"]), bot_token=data.bot_token
        )
    except Exception as exc:
        await record_action(
            db,
            event_type="integration_connected",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={
                "type": "slack",
                "request_id": request_id,
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail=f"Slack connection failed ({type(exc).__name__}). Check your bot token and scopes.",
        ) from exc

    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=info["id"],
        payload_json={"type": "slack", "team": info.get("team"), "request_id": request_id, "status": "ok"},
    )
    return SlackStatusRead(connected=True, team=info.get("team"), channels_tracked=0)


@router.get("/slack/status", response_model=SlackStatusRead)
async def slack_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SlackStatusRead:
    status = await slack_service.get_slack_status(db, org_id=int(actor["org_id"]))
    return SlackStatusRead(**status)


@router.post("/slack/sync", response_model=SlackSyncResult)
async def slack_sync(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SlackSyncResult:
    org_id = int(actor["org_id"])
    request_id = get_current_request_id()
    scope = f"slack_sync:{org_id}"
    fingerprint = build_fingerprint({"org_id": org_id, "action": "slack_sync"})
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cast(SlackSyncResult, SlackSyncResult.model_validate(cached))
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = await slack_service.sync_slack_messages(db, org_id=org_id)
    if result["error"]:
        await record_action(
            db,
            event_type="slack_synced",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={"request_id": request_id, "status": "error", "error": result["error"]},
        )
        raise HTTPException(status_code=400, detail=result["error"])

    await record_action(
        db,
        event_type="slack_synced",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={
            "request_id": request_id,
            "status": "ok",
            "channels_synced": result["channels_synced"],
            "messages_read": result["messages_read"],
        },
    )
    status = await slack_service.get_slack_status(db, org_id=org_id)
    response = SlackSyncResult(
        channels_synced=result["channels_synced"],
        messages_read=result["messages_read"],
        last_sync_at=status.get("last_sync_at"),
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response


@router.post("/slack/send")
async def slack_send(
    data: SlackSendRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    request_id = get_current_request_id()
    try:
        result = await slack_service.send_to_slack(
            db, org_id=int(actor["org_id"]), channel_id=data.channel_id, text=data.text
        )
    except Exception as exc:
        await record_action(
            db,
            event_type="slack_message_sent",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={
                "request_id": request_id,
                "status": "error",
                "channel_id": data.channel_id,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail=f"Slack send failed ({type(exc).__name__}).",
        ) from exc

    await record_action(
        db,
        event_type="slack_message_sent",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={"request_id": request_id, "status": "ok", "channel_id": data.channel_id, "text_preview": data.text[:100]},
    )
    return {"ok": True, "ts": result.get("ts")}
