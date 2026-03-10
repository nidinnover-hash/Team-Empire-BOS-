"""Sales forecast rollup endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import forecast_rollup as svc

router = APIRouter(prefix="/forecast-rollups", tags=["forecast-rollups"])


class RollupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    period: str
    period_type: str
    group_by: str
    group_value: str
    committed: float
    best_case: float
    pipeline: float
    weighted_pipeline: float
    closed_won: float
    target: float
    attainment_pct: float
    created_at: datetime
    updated_at: datetime


class RollupCreate(BaseModel):
    period: str
    period_type: str = "monthly"
    group_by: str = "team"
    group_value: str
    committed: float = 0.0
    best_case: float = 0.0
    pipeline: float = 0.0
    weighted_pipeline: float = 0.0
    closed_won: float = 0.0
    target: float = 0.0
    attainment_pct: float = 0.0


@router.post("", response_model=RollupOut, status_code=201)
async def upsert_rollup(
    body: RollupCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.upsert_rollup(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[RollupOut])
async def list_rollups(
    period: str | None = None, group_by: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_rollups(db, actor["org_id"], period=period, group_by=group_by)


@router.get("/summary/{period}")
async def get_period_summary(
    period: str, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_period_summary(db, actor["org_id"], period)


@router.get("/{rollup_id}", response_model=RollupOut)
async def get_rollup(
    rollup_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_rollup(db, rollup_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Rollup not found")
    return row
