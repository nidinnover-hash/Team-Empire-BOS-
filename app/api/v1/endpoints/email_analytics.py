"""Email analytics endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import email_analytics as svc

router = APIRouter(prefix="/email-analytics", tags=["email-analytics"])


class EmailEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    event_type: str
    email_id: int | None = None
    contact_id: int | None = None
    link_url: str | None = None
    user_agent: str | None = None
    created_at: datetime


class EmailEventCreate(BaseModel):
    event_type: str
    email_id: int | None = None
    contact_id: int | None = None
    link_url: str | None = None
    user_agent: str | None = None


@router.post("", response_model=EmailEventOut, status_code=201)
async def record_event(
    body: EmailEventCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.record_event(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[EmailEventOut])
async def list_events(
    email_id: int | None = None,
    contact_id: int | None = None,
    event_type: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_events(db, actor["org_id"], email_id=email_id, contact_id=contact_id, event_type=event_type, limit=limit)


@router.get("/overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_overview(db, actor["org_id"])


@router.get("/email/{email_id}/metrics")
async def get_email_metrics(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_email_metrics(db, actor["org_id"], email_id)


@router.get("/contact/{contact_id}/engagement")
async def get_contact_engagement(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_contact_engagement(db, actor["org_id"], contact_id)
