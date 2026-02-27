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
    except CONNECT_EXCEPTIONS as exc:
        await handle_connect_error(db, integration_type="notion", actor=actor, exc=exc)
    await audit_connect_success(db, integration_type="notion", actor=actor, entity_id=info["id"])
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
    except (httpx.HTTPError, RuntimeError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        raise HTTPException(status_code=502, detail="Notion sync failed due to upstream error. Retry shortly.") from exc
    normalized = normalize_sync_result(
        result,
        integration_type="notion",
        required_int_fields=("pages_synced", "notes_created"),
    )
    await audit_sync(
        db, event_type="notion_synced", actor=actor,
        payload={"pages_synced": normalized["pages_synced"], "notes_created": normalized["notes_created"]},
    )
    return NotionSyncResult(
        pages_synced=normalized["pages_synced"],
        notes_created=normalized["notes_created"],
        last_sync_at=result.get("last_sync_at"),
    )
