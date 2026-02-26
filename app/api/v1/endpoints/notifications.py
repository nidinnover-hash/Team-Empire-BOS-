"""Notification endpoints — list, count, mark read, SSE stream."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.db.session import AsyncSessionLocal
from app.schemas.notification import (
    NotificationCountRead,
    NotificationListRead,
    NotificationMarkReadRequest,
    NotificationRead,
)
from app.services import notification as notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListRead)
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> NotificationListRead:
    org_id = int(actor["org_id"])
    user_id = int(actor["id"])
    items = await notification_service.list_notifications(
        db, org_id, user_id, unread_only=unread_only, limit=limit,
    )
    unread = await notification_service.get_unread_count(db, org_id, user_id)
    return NotificationListRead(
        count=len(items),
        unread_count=unread,
        items=[NotificationRead.model_validate(n) for n in items],
    )


@router.get("/count", response_model=NotificationCountRead)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> NotificationCountRead:
    org_id = int(actor["org_id"])
    user_id = int(actor["id"])
    count = await notification_service.get_unread_count(db, org_id, user_id)
    return NotificationCountRead(unread_count=count)


@router.post("/mark-read")
async def mark_notifications_read(
    payload: NotificationMarkReadRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> dict:
    org_id = int(actor["org_id"])
    user_id = int(actor["id"])
    if payload.notification_ids:
        updated = await notification_service.mark_read(db, org_id, payload.notification_ids, user_id=user_id)
    else:
        user_id = int(actor["id"])
        updated = await notification_service.mark_all_read(db, org_id, user_id)
    await db.commit()
    return {"ok": True, "marked_read": updated}


@router.get("/stream")
async def notification_stream(
    request: Request,
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> StreamingResponse:
    """SSE stream that pushes unread count every 5 seconds.

    Uses fresh DB sessions per poll to avoid holding a stale request-scoped
    session open for the lifetime of the SSE connection.
    """
    org_id = int(actor["org_id"])
    user_id = int(actor["id"])

    async def event_generator():
        last_count = -1
        while True:
            if await request.is_disconnected():
                break
            try:
                async with AsyncSessionLocal() as db:
                    count = await notification_service.get_unread_count(db, org_id, user_id)
            except Exception:
                count = last_count  # keep last known value on transient DB errors
            if count != last_count:
                data = json.dumps({"unread_count": count})
                yield f"data: {data}\n\n"
                last_count = count
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
