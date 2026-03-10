"""Customer health score endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import customer_health as svc

router = APIRouter(prefix="/customer-health", tags=["customer-health"])


class HealthScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    contact_id: int
    overall_score: int
    usage_score: int
    engagement_score: int
    support_score: int
    payment_score: int
    risk_level: str
    previous_score: int
    created_at: datetime
    updated_at: datetime


class UpsertBody(BaseModel):
    contact_id: int
    usage_score: int = 0
    engagement_score: int = 0
    support_score: int = 0
    payment_score: int = 0
    factors: dict | None = None


@router.post("", response_model=HealthScoreOut, status_code=201)
async def upsert_score(
    body: UpsertBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.upsert_score(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[HealthScoreOut])
async def list_scores(
    risk_level: str | None = None, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_scores(db, actor["org_id"], risk_level=risk_level, limit=limit)


@router.get("/summary")
async def get_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_summary(db, actor["org_id"])


@router.get("/{contact_id}", response_model=HealthScoreOut)
async def get_score(
    contact_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_score(db, contact_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Health score not found")
    return row
