"""Drip campaign analytics endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import drip_analytics as svc

router = APIRouter(prefix="/drip-analytics", tags=["drip-analytics"])


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    campaign_id: int
    step_id: int
    enrollment_id: int
    contact_id: int
    event_type: str
    metadata_json: str | None = None
    created_at: datetime


class EventCreate(BaseModel):
    campaign_id: int
    step_id: int
    enrollment_id: int
    contact_id: int
    event_type: str
    metadata_json: str | None = None


@router.post("/events", response_model=EventOut, status_code=201)
async def record_event(
    body: EventCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.record_event(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("/events", response_model=list[EventOut])
async def list_events(
    campaign_id: int | None = None, step_id: int | None = None,
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_events(db, actor["org_id"], campaign_id=campaign_id, step_id=step_id, event_type=event_type)


@router.get("/steps/{campaign_id}")
async def get_step_stats(
    campaign_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_step_stats(db, actor["org_id"], campaign_id)


@router.get("/summary/{campaign_id}")
async def get_campaign_summary(
    campaign_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_campaign_summary(db, actor["org_id"], campaign_id)
