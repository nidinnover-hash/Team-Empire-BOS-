"""Webhook delivery log — track outbound webhook delivery attempts."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import webhook_delivery as wd_service

router = APIRouter(prefix="/webhook-deliveries", tags=["Webhook Deliveries"])


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    webhook_id: int
    event_type: str
    url: str
    response_status: int | None = None
    attempt_number: int
    status: str
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


@router.get("", response_model=list[WebhookDeliveryRead])
async def list_webhook_deliveries(
    webhook_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[WebhookDeliveryRead]:
    items = await wd_service.list_deliveries(
        db, organization_id=actor["org_id"], webhook_id=webhook_id, status=status, limit=limit,
    )
    return [WebhookDeliveryRead.model_validate(d, from_attributes=True) for d in items]


@router.get("/stats")
async def webhook_delivery_stats(
    webhook_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await wd_service.get_delivery_stats(db, organization_id=actor["org_id"], webhook_id=webhook_id)
