"""API rate limiting config — per-org configurable limits with usage tracking."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import rate_limit_config as rl_service

router = APIRouter(prefix="/rate-limits", tags=["Rate Limits"])


class RateLimitCreate(BaseModel):
    name: str = Field(..., max_length=200)
    endpoint_pattern: str = Field(..., max_length=200)
    requests_per_minute: int = Field(60, ge=1)
    requests_per_hour: int = Field(1000, ge=1)
    burst_limit: int = Field(10, ge=1)


class RateLimitUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    requests_per_minute: int | None = Field(None, ge=1)
    requests_per_hour: int | None = Field(None, ge=1)
    burst_limit: int | None = Field(None, ge=1)
    is_active: bool | None = None


class RateLimitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    endpoint_pattern: str
    requests_per_minute: int
    requests_per_hour: int
    burst_limit: int
    is_active: bool
    total_requests_tracked: int
    total_throttled: int
    created_at: datetime | None = None


@router.get("", response_model=list[RateLimitRead])
async def list_rate_limits(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[RateLimitRead]:
    items = await rl_service.list_configs(db, organization_id=actor["org_id"], active_only=active_only)
    return [RateLimitRead.model_validate(c, from_attributes=True) for c in items]


@router.post("", response_model=RateLimitRead, status_code=201)
async def create_rate_limit(
    data: RateLimitCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RateLimitRead:
    config = await rl_service.create_config(db, organization_id=actor["org_id"], **data.model_dump())
    return RateLimitRead.model_validate(config, from_attributes=True)


@router.patch("/{config_id}", response_model=RateLimitRead)
async def update_rate_limit(
    config_id: int,
    data: RateLimitUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RateLimitRead:
    config = await rl_service.update_config(
        db, config_id=config_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")
    return RateLimitRead.model_validate(config, from_attributes=True)


@router.delete("/{config_id}", status_code=204)
async def delete_rate_limit(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await rl_service.delete_config(db, config_id=config_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Config not found")


@router.get("/usage")
async def get_usage_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[dict]:
    return await rl_service.get_usage_summary(db, organization_id=actor["org_id"])
