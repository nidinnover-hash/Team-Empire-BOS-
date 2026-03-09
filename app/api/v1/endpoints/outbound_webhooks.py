"""Outbound webhooks — configurable push to external systems on events."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import outbound_webhook as wh_service

router = APIRouter(prefix="/outbound-webhooks", tags=["Outbound Webhooks"])


class OutboundWebhookCreate(BaseModel):
    name: str = Field(..., max_length=200)
    url: str = Field(..., max_length=2048)
    event_types: list[str] = Field(default_factory=lambda: ["*"])
    headers: dict[str, str] | None = None
    secret: str | None = Field(None, max_length=200)


class OutboundWebhookUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    url: str | None = None
    event_types: list[str] | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None


class OutboundWebhookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    event_types_json: str
    is_active: bool
    failure_count: int
    last_triggered_at: datetime | None = None
    created_at: datetime | None = None


@router.get("", response_model=list[OutboundWebhookRead])
async def list_outbound_webhooks(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[OutboundWebhookRead]:
    items = await wh_service.list_webhooks(db, organization_id=actor["org_id"], active_only=active_only)
    return [OutboundWebhookRead.model_validate(w, from_attributes=True) for w in items]


@router.post("", response_model=OutboundWebhookRead, status_code=201)
async def create_outbound_webhook(
    data: OutboundWebhookCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> OutboundWebhookRead:
    wh = await wh_service.create_webhook(
        db, organization_id=actor["org_id"],
        name=data.name, url=data.url, event_types=data.event_types,
        headers=data.headers, secret=data.secret,
    )
    return OutboundWebhookRead.model_validate(wh, from_attributes=True)


@router.patch("/{webhook_id}", response_model=OutboundWebhookRead)
async def update_outbound_webhook(
    webhook_id: int,
    data: OutboundWebhookUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> OutboundWebhookRead:
    wh = await wh_service.update_webhook(
        db, webhook_id=webhook_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if wh is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return OutboundWebhookRead.model_validate(wh, from_attributes=True)


@router.delete("/{webhook_id}", status_code=204)
async def delete_outbound_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await wh_service.delete_webhook(db, webhook_id=webhook_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")


@router.get("/test-match")
async def test_webhook_match(
    event_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Test which webhooks would fire for a given event type."""
    matched = await wh_service.get_matching_webhooks(db, organization_id=actor["org_id"], event_type=event_type)
    return {
        "event_type": event_type,
        "matching_webhooks": [{"id": w.id, "name": w.name, "url": w.url} for w in matched],
    }
