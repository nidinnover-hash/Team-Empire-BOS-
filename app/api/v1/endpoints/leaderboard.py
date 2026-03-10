"""Sales leaderboard endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import sales_leaderboard as svc

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    user_id: int
    period: str
    period_type: str
    total_revenue: float
    deals_closed: int
    deals_created: int
    activities_count: int
    rank: int
    created_at: datetime
    updated_at: datetime


class UpsertBody(BaseModel):
    user_id: int
    period: str
    period_type: str = "monthly"
    total_revenue: float = 0
    deals_closed: int = 0
    deals_created: int = 0
    activities_count: int = 0


@router.post("", response_model=EntryOut, status_code=201)
async def upsert_entry(
    body: UpsertBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.upsert_entry(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[EntryOut])
async def get_leaderboard(
    period: str, period_type: str = "monthly",
    sort_by: str = "total_revenue",
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_leaderboard(db, actor["org_id"], period=period, period_type=period_type, sort_by=sort_by)


@router.get("/history/{user_id}", response_model=list[EntryOut])
async def get_user_history(
    user_id: int, period_type: str = "monthly", limit: int = 12,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_user_history(db, actor["org_id"], user_id, period_type=period_type, limit=limit)
