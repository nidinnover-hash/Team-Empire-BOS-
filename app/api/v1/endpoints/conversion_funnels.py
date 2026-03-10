"""Pipeline conversion funnel endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import conversion_funnel as svc

router = APIRouter(prefix="/conversion-funnels", tags=["conversion-funnels"])


class FunnelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    period: str
    period_type: str
    from_stage: str
    to_stage: str
    entered_count: int
    converted_count: int
    conversion_rate: float
    avg_time_hours: float
    median_time_hours: float
    created_at: datetime
    updated_at: datetime


class FunnelCreate(BaseModel):
    period: str
    period_type: str = "monthly"
    from_stage: str
    to_stage: str
    entered_count: int = 0
    converted_count: int = 0
    conversion_rate: float = 0.0
    avg_time_hours: float = 0.0
    median_time_hours: float = 0.0


@router.post("", response_model=FunnelOut, status_code=201)
async def upsert_stage(
    body: FunnelCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.upsert_stage(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[FunnelOut])
async def list_funnel(
    period: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_funnel(db, actor["org_id"], period=period)


@router.get("/summary/{period}")
async def get_funnel_summary(
    period: str, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_funnel_summary(db, actor["org_id"], period)


@router.get("/bottlenecks/{period}")
async def get_bottlenecks(
    period: str, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_bottlenecks(db, actor["org_id"], period)
