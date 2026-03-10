"""Win/loss analysis endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import win_loss_analysis as svc

router = APIRouter(prefix="/win-loss", tags=["win-loss"])


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    deal_id: int
    outcome: str
    primary_reason: str
    secondary_reason: str | None = None
    competitor_id: int | None = None
    deal_amount: float
    sales_cycle_days: int
    notes: str | None = None
    recorded_by_user_id: int
    created_at: datetime


class RecordCreate(BaseModel):
    deal_id: int
    outcome: str
    primary_reason: str
    secondary_reason: str | None = None
    competitor_id: int | None = None
    deal_amount: float = 0.0
    sales_cycle_days: int = 0
    notes: str | None = None


@router.post("", response_model=RecordOut, status_code=201)
async def record_outcome(
    body: RecordCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.record_outcome(db, organization_id=actor["org_id"], recorded_by_user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[RecordOut])
async def list_records(
    outcome: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_records(db, actor["org_id"], outcome=outcome)


@router.get("/analytics")
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_analytics(db, actor["org_id"])


@router.get("/top-reasons/{outcome}")
async def get_top_reasons(
    outcome: str, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_top_reasons(db, actor["org_id"], outcome)


@router.get("/{record_id}", response_model=RecordOut)
async def get_record(
    record_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_record(db, record_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Record not found")
    return row
