"""Contact lifecycle stages — track progression through sales funnel."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import contact_lifecycle as lc_service

router = APIRouter(prefix="/contact-lifecycle", tags=["Contact Lifecycle"])


class StageTransition(BaseModel):
    contact_id: int
    to_stage: str = Field(..., pattern=r"^(lead|mql|sql|opportunity|customer|churned)$")
    from_stage: str | None = None
    reason: str | None = Field(None, max_length=500)


class LifecycleEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    from_stage: str | None = None
    to_stage: str
    changed_by_user_id: int | None = None
    reason: str | None = None
    created_at: datetime | None = None


@router.post("/transition", response_model=LifecycleEventRead, status_code=201)
async def transition_stage(
    data: StageTransition,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> LifecycleEventRead:
    event = await lc_service.transition_stage(
        db, organization_id=actor["org_id"], contact_id=data.contact_id,
        to_stage=data.to_stage, from_stage=data.from_stage,
        changed_by=int(actor["id"]), reason=data.reason,
    )
    return LifecycleEventRead.model_validate(event, from_attributes=True)


@router.get("/history/{contact_id}", response_model=list[LifecycleEventRead])
async def get_contact_history(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[LifecycleEventRead]:
    items = await lc_service.get_contact_history(db, organization_id=actor["org_id"], contact_id=contact_id)
    return [LifecycleEventRead.model_validate(e, from_attributes=True) for e in items]


@router.get("/current/{contact_id}")
async def get_current_stage(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    stage = await lc_service.get_current_stage(db, organization_id=actor["org_id"], contact_id=contact_id)
    return {"contact_id": contact_id, "current_stage": stage}


@router.get("/counts")
async def get_stage_counts(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await lc_service.get_stage_counts(db, organization_id=actor["org_id"])
