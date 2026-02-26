"""Notification endpoints — list, count, mark read."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
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
    limit: int = 50,
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
    if payload.notification_ids:
        updated = await notification_service.mark_read(db, org_id, payload.notification_ids)
    else:
        user_id = int(actor["id"])
        updated = await notification_service.mark_all_read(db, org_id, user_id)
    await db.commit()
    return {"ok": True, "marked_read": updated}
