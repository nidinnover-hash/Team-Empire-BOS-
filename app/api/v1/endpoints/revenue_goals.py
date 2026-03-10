"""Revenue goal tracking endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import revenue_goal as svc

router = APIRouter(prefix="/revenue-goals", tags=["revenue-goals"])


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    scope: str
    scope_id: int | None = None
    period: str
    period_type: str
    target_amount: float
    current_amount: float
    stretch_amount: float
    attainment_pct: float
    gap: float
    status: str
    created_at: datetime
    updated_at: datetime


class GoalCreate(BaseModel):
    scope: str = "org"
    scope_id: int | None = None
    period: str
    period_type: str = "quarterly"
    target_amount: float = 0.0
    current_amount: float = 0.0
    stretch_amount: float = 0.0


@router.post("", response_model=GoalOut, status_code=201)
async def create_goal(
    body: GoalCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.create_goal(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[GoalOut])
async def list_goals(
    scope: str | None = None, period: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_goals(db, actor["org_id"], scope=scope, period=period)


@router.put("/{goal_id}/progress", response_model=GoalOut)
async def update_progress(
    goal_id: int, current_amount: float,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_progress(db, goal_id, actor["org_id"], current_amount)
    if not row:
        raise HTTPException(404, "Goal not found")
    return row


@router.get("/gap-analysis/{period}")
async def get_gap_analysis(
    period: str, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_gap_analysis(db, actor["org_id"], period)
