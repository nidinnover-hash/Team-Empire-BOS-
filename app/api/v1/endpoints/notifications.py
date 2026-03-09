"""Notification endpoints — list, count, mark read, SSE stream."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_api_user, get_current_web_user, get_db
from app.core.rbac import require_roles
from app.db.session import AsyncSessionLocal
from app.schemas.notification import (
    NotificationCountRead,
    NotificationListRead,
    NotificationMarkReadRequest,
    NotificationMarkReadResponse,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
)
from app.services import notification as notification_service
from app.services import notification_preference as pref_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])
_ALLOWED_NOTIFICATION_ROLES = {"CEO", "ADMIN", "MANAGER", "EMPLOYEE"}


def _ensure_notification_role(actor: dict) -> None:
    role = str(actor.get("role", ""))
    if role not in _ALLOWED_NOTIFICATION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' does not have access",
        )


async def _get_notification_stream_actor(
    request: Request,
    token: str | None = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # EventSource cannot set headers, so accept token as a query param too
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header.split(" ", 1)[1].strip()
        return await get_current_api_user(request=request, token=bearer_token, db=db)
    if token:
        return await get_current_api_user(request=request, token=token, db=db)
    session_token = request.cookies.get("pc_session")
    if session_token:
        return await get_current_web_user(request=request, session_token=session_token, db=db)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")


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


@router.post("/mark-read", response_model=NotificationMarkReadResponse)
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
        updated = await notification_service.mark_all_read(db, org_id, user_id)
    await db.commit()
    return NotificationMarkReadResponse(ok=True, marked_read=updated)


@router.get("/preferences", response_model=list[NotificationPreferenceRead])
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> list[NotificationPreferenceRead]:
    """Get notification preferences for all categories (with defaults)."""
    prefs = await pref_service.get_preferences_with_defaults(
        db, user_id=int(actor["id"]), organization_id=int(actor["org_id"]),
    )
    return [NotificationPreferenceRead(**p) for p in prefs]


@router.patch("/preferences", response_model=NotificationPreferenceRead)
async def update_preference(
    data: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> NotificationPreferenceRead:
    """Update notification preference for a specific category."""
    pref = await pref_service.upsert_preference(
        db,
        user_id=int(actor["id"]),
        organization_id=int(actor["org_id"]),
        event_category=data.event_category,
        in_app=data.in_app,
        email=data.email,
        slack=data.slack,
        min_severity=data.min_severity,
        muted=data.muted,
    )
    return NotificationPreferenceRead(
        event_category=pref.event_category,
        in_app=pref.in_app,
        email=pref.email,
        slack=pref.slack,
        min_severity=pref.min_severity,
        muted=pref.muted,
    )


@router.get("/stream")
async def notification_stream(
    request: Request,
    actor: dict = Depends(_get_notification_stream_actor),
) -> StreamingResponse:
    """SSE stream that pushes unread count every 5 seconds.

    Uses fresh DB sessions per poll to avoid holding a stale request-scoped
    session open for the lifetime of the SSE connection.
    """
    _ensure_notification_role(actor)
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
            except (OSError, RuntimeError, ValueError, TypeError) as exc:
                logger.debug("SSE unread-count probe failed (%s), keeping last value", type(exc).__name__)
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


@router.get("/live")
async def notification_live_stream(
    request: Request,
    actor: dict = Depends(_get_notification_stream_actor),
) -> StreamingResponse:
    """Enhanced SSE stream: pushes unread count + latest notifications on change.

    Events:
      - ``data: {"unread_count": N, "notifications": [...]}`` when new items arrive.
    """
    _ensure_notification_role(actor)
    org_id = int(actor["org_id"])
    user_id = int(actor["id"])

    async def event_generator():
        last_count = -1
        last_top_id = -1
        while True:
            if await request.is_disconnected():
                break
            try:
                async with AsyncSessionLocal() as db:
                    count = await notification_service.get_unread_count(db, org_id, user_id)
                    items = await notification_service.list_notifications(
                        db, org_id, user_id, unread_only=True, limit=10,
                    )
                    top_id = items[0].id if items else 0
            except (OSError, RuntimeError, ValueError, TypeError) as exc:
                logger.debug("SSE live probe failed (%s)", type(exc).__name__)
                await asyncio.sleep(5)
                continue

            if count != last_count or top_id != last_top_id:
                payload = {
                    "unread_count": count,
                    "notifications": [
                        {
                            "id": n.id,
                            "type": n.type,
                            "severity": n.severity,
                            "title": n.title,
                            "message": n.message,
                            "source": n.source,
                            "created_at": n.created_at.isoformat() if n.created_at else None,
                        }
                        for n in items[:5]
                    ],
                }
                yield f"data: {json.dumps(payload)}\n\n"
                last_count = count
                last_top_id = top_id
            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/run-alerts")
async def run_alert_checks(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Run proactive alert checks: budget overruns, stale contacts, failed syncs."""
    from app.services.alert_engine import run_alert_checks as _run_checks
    return await _run_checks(db, organization_id=int(actor["org_id"]))
