"""Webhook retry queue — exponential backoff retry management."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import webhook_retry as wr_service

router = APIRouter(prefix="/webhook-retries", tags=["Webhook Retries"])


class RetryCreate(BaseModel):
    webhook_id: int
    event_type: str = Field(..., max_length=100)
    payload: dict
    delivery_id: int | None = None
    max_attempts: int = Field(5, ge=1, le=10)


class RetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    webhook_id: int
    event_type: str
    payload_json: str
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None = None
    last_error: str | None = None
    status: str
    created_at: datetime | None = None


@router.get("", response_model=list[RetryRead])
async def list_retries(
    status: str | None = Query(None),
    webhook_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[RetryRead]:
    items = await wr_service.list_retries(
        db, organization_id=actor["org_id"], status=status, webhook_id=webhook_id, limit=limit,
    )
    return [RetryRead.model_validate(r, from_attributes=True) for r in items]


@router.post("", response_model=RetryRead, status_code=201)
async def enqueue_retry(
    data: RetryCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RetryRead:
    retry = await wr_service.enqueue_retry(
        db, organization_id=actor["org_id"], webhook_id=data.webhook_id,
        event_type=data.event_type, payload=data.payload,
        delivery_id=data.delivery_id, max_attempts=data.max_attempts,
    )
    return RetryRead.model_validate(retry, from_attributes=True)


@router.get("/pending", response_model=list[RetryRead])
async def get_pending_retries(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[RetryRead]:
    items = await wr_service.get_pending_retries(db, organization_id=actor["org_id"])
    return [RetryRead.model_validate(r, from_attributes=True) for r in items]


@router.get("/stats")
async def retry_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await wr_service.get_retry_stats(db, organization_id=actor["org_id"])
