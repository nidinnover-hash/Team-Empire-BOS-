"""Deal velocity — stage transition tracking and bottleneck analysis."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import deal_velocity as dv_service

router = APIRouter(prefix="/deal-velocity", tags=["Deal Velocity"])


class TransitionCreate(BaseModel):
    deal_id: int
    from_stage: str | None = None
    to_stage: str = Field(..., max_length=50)
    hours_in_stage: float | None = None


class TransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deal_id: int
    from_stage: str | None = None
    to_stage: str
    hours_in_stage: float | None = None
    changed_by_user_id: int | None = None
    created_at: datetime | None = None


@router.post("/transition", response_model=TransitionRead, status_code=201)
async def record_transition(
    data: TransitionCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> TransitionRead:
    t = await dv_service.record_transition(
        db, organization_id=actor["org_id"], deal_id=data.deal_id,
        from_stage=data.from_stage, to_stage=data.to_stage,
        hours_in_stage=data.hours_in_stage, changed_by=int(actor["id"]),
    )
    return TransitionRead.model_validate(t, from_attributes=True)


@router.get("/history/{deal_id}", response_model=list[TransitionRead])
async def get_deal_history(
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[TransitionRead]:
    items = await dv_service.get_deal_history(db, organization_id=actor["org_id"], deal_id=deal_id)
    return [TransitionRead.model_validate(t, from_attributes=True) for t in items]


@router.get("/velocity")
async def get_stage_velocity(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await dv_service.get_stage_velocity(db, organization_id=actor["org_id"])


@router.get("/bottlenecks")
async def get_bottlenecks(
    threshold_hours: float = Query(48, ge=1),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    return await dv_service.get_bottlenecks(db, organization_id=actor["org_id"], threshold_hours=threshold_hours)
