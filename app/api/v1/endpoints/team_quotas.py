"""Team quotas — sales quota management with progress tracking."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import team_quota as tq_service

router = APIRouter(prefix="/team-quotas", tags=["Team Quotas"])


class QuotaCreate(BaseModel):
    user_id: int
    period: str = Field(..., pattern=r"^(monthly|quarterly|yearly)$")
    period_start: datetime
    period_end: datetime
    quota_type: str = Field("revenue", pattern=r"^(revenue|deals|contacts)$")
    target_value: float = Field(..., gt=0)


class QuotaUpdate(BaseModel):
    target_value: float | None = Field(None, gt=0)
    is_active: bool | None = None


class QuotaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    period: str
    period_start: datetime
    period_end: datetime
    quota_type: str
    target_value: float
    current_value: float
    is_active: bool
    created_at: datetime | None = None


class ProgressUpdate(BaseModel):
    value: float


@router.get("", response_model=list[QuotaRead])
async def list_quotas(
    user_id: int | None = Query(None),
    period: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[QuotaRead]:
    items = await tq_service.list_quotas(
        db, organization_id=actor["org_id"], user_id=user_id, period=period,
    )
    return [QuotaRead.model_validate(q, from_attributes=True) for q in items]


@router.post("", response_model=QuotaRead, status_code=201)
async def create_quota(
    data: QuotaCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> QuotaRead:
    quota = await tq_service.create_quota(db, organization_id=actor["org_id"], **data.model_dump())
    return QuotaRead.model_validate(quota, from_attributes=True)


@router.patch("/{quota_id}", response_model=QuotaRead)
async def update_quota(
    quota_id: int,
    data: QuotaUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> QuotaRead:
    quota = await tq_service.update_quota(
        db, quota_id=quota_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if quota is None:
        raise HTTPException(status_code=404, detail="Quota not found")
    return QuotaRead.model_validate(quota, from_attributes=True)


@router.patch("/{quota_id}/progress", response_model=QuotaRead)
async def update_progress(
    quota_id: int,
    data: ProgressUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> QuotaRead:
    quota = await tq_service.update_progress(
        db, quota_id=quota_id, organization_id=actor["org_id"], value=data.value,
    )
    if quota is None:
        raise HTTPException(status_code=404, detail="Quota not found")
    return QuotaRead.model_validate(quota, from_attributes=True)


@router.delete("/{quota_id}", status_code=204)
async def delete_quota(
    quota_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await tq_service.delete_quota(db, quota_id=quota_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Quota not found")


@router.get("/progress")
async def get_team_progress(
    period: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    return await tq_service.get_team_progress(db, organization_id=actor["org_id"], period=period)
