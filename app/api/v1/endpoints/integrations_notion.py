from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    NotionConnectRequest,
    NotionStatusRead,
    NotionSyncResult,
)
from app.services import notion_service

router = APIRouter(tags=["Integrations"])


@router.post("/notion/connect", response_model=NotionStatusRead, status_code=201)
async def notion_connect(
    data: NotionConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> NotionStatusRead:
    try:
        info = await notion_service.connect_notion(
            db, org_id=int(actor["org_id"]), api_token=data.api_token,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Notion connection failed: {type(exc).__name__}") from exc
    await record_action(
        db, event_type="integration_connected", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=info["id"], payload_json={"type": "notion", "status": "ok"},
    )
    return NotionStatusRead(connected=True, bot_name=info.get("bot_name"))


@router.get("/notion/status", response_model=NotionStatusRead)
async def notion_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> NotionStatusRead:
    status = await notion_service.get_notion_status(db, org_id=int(actor["org_id"]))
    return NotionStatusRead(**status)


@router.post("/notion/sync", response_model=NotionSyncResult)
async def notion_sync(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> NotionSyncResult:
    try:
        result = await notion_service.sync_pages_to_notes(db, org_id=int(actor["org_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_action(
        db, event_type="notion_synced", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=None, payload_json={"pages_synced": result["pages_synced"], "notes_created": result["notes_created"]},
    )
    return NotionSyncResult(**result)
