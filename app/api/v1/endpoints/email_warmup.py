"""Email warmup tracking endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import email_warmup as svc

router = APIRouter(prefix="/email-warmup", tags=["email-warmup"])


class WarmupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    email_address: str
    domain: str
    daily_limit: int
    current_daily: int
    target_daily: int
    ramp_increment: int
    warmup_day: int
    reputation_score: int
    is_active: bool
    started_at: datetime
    created_at: datetime
    updated_at: datetime


class WarmupCreate(BaseModel):
    email_address: str
    domain: str
    daily_limit: int = 5
    target_daily: int = 50
    ramp_increment: int = 2


@router.post("", response_model=WarmupOut, status_code=201)
async def create_warmup(
    body: WarmupCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.create_warmup(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[WarmupOut])
async def list_warmups(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_warmups(db, actor["org_id"], is_active=is_active)


@router.put("/{warmup_id}/advance", response_model=WarmupOut)
async def advance_day(
    warmup_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    row = await svc.advance_day(db, warmup_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Warmup not found")
    return row


@router.get("/status")
async def get_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_status(db, actor["org_id"])
