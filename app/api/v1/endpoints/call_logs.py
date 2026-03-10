"""Call logging endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import call_log as svc

router = APIRouter(prefix="/call-logs", tags=["call-logs"])


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    user_id: int
    contact_id: int | None = None
    deal_id: int | None = None
    direction: str
    duration_seconds: int
    outcome: str
    recording_url: str | None = None
    notes: str | None = None
    called_at: datetime
    created_at: datetime


class CallCreate(BaseModel):
    contact_id: int | None = None
    deal_id: int | None = None
    direction: str = "outbound"
    duration_seconds: int = 0
    outcome: str = "completed"
    recording_url: str | None = None
    notes: str | None = None


@router.post("", response_model=CallOut, status_code=201)
async def create_call(
    body: CallCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_call(db, organization_id=actor["org_id"], user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[CallOut])
async def list_calls(
    contact_id: int | None = None, deal_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_calls(db, actor["org_id"], contact_id=contact_id, deal_id=deal_id)


@router.get("/stats")
async def get_stats(
    user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_stats(db, actor["org_id"], user_id=user_id)


@router.get("/{call_id}", response_model=CallOut)
async def get_call(
    call_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_call(db, call_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Call not found")
    return row
