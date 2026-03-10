"""Webhook event log endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import webhook_event as svc

router = APIRouter(prefix="/webhook-events", tags=["webhook-events"])


class WebhookEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    source: str
    event_type: str
    status: str
    error_message: str | None = None
    processed_at: datetime | None = None
    created_at: datetime


class CaptureBody(BaseModel):
    source: str
    event_type: str
    payload: dict | None = None
    headers: dict | None = None


@router.post("", response_model=WebhookEventOut, status_code=201)
async def capture_event(
    body: CaptureBody,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.capture_event(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[WebhookEventOut])
async def list_events(
    source: str | None = None,
    status: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_events(db, actor["org_id"], source=source, status=status, limit=limit)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_stats(db, actor["org_id"])


@router.get("/{event_id}", response_model=WebhookEventOut)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_event(db, event_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Event not found")
    return row


@router.post("/{event_id}/process", response_model=WebhookEventOut)
async def mark_processed(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.mark_processed(db, event_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Event not found")
    return row


@router.post("/{event_id}/replay", response_model=WebhookEventOut, status_code=201)
async def replay_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.replay_event(db, event_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Event not found")
    return row
