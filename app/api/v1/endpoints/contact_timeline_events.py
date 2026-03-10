"""Contact timeline events endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import contact_timeline_events as svc

router = APIRouter(prefix="/contact-timeline", tags=["contact-timeline"])


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    contact_id: int
    event_type: str
    event_source: str
    title: str
    description: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    actor_user_id: int | None = None
    occurred_at: datetime
    created_at: datetime


class TimelineEventCreate(BaseModel):
    contact_id: int
    event_type: str
    event_source: str = "manual"
    title: str
    description: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None


@router.post("/events", response_model=TimelineEventOut, status_code=201)
async def add_event(
    body: TimelineEventCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.add_event(db, organization_id=actor["org_id"], actor_user_id=actor["id"], **body.model_dump())


@router.get("/events/{contact_id}", response_model=list[TimelineEventOut])
async def list_events(
    contact_id: int, event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_events(db, actor["org_id"], contact_id, event_type=event_type)


@router.get("/summary/{contact_id}")
async def get_activity_summary(
    contact_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_activity_summary(db, actor["org_id"], contact_id)
