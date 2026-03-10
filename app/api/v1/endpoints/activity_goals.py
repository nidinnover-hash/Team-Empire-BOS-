"""Activity goals / quotas endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import activity_goal as svc

router = APIRouter(prefix="/activity-goals", tags=["activity-goals"])


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    user_id: int
    activity_type: str
    period: str
    period_type: str
    target: int
    current: int
    streak: int
    best_streak: int
    created_at: datetime
    updated_at: datetime


class GoalCreate(BaseModel):
    user_id: int
    activity_type: str
    period: str
    period_type: str = "weekly"
    target: int = 0


class RecordBody(BaseModel):
    count: int = 1


class ResetBody(BaseModel):
    new_period: str


@router.post("", response_model=GoalOut, status_code=201)
async def create_goal(
    body: GoalCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_goal(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[GoalOut])
async def list_goals(
    user_id: int | None = None, activity_type: str | None = None,
    period: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_goals(db, actor["org_id"], user_id=user_id, activity_type=activity_type, period=period)


@router.get("/progress/{user_id}")
async def get_progress(
    user_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_progress(db, actor["org_id"], user_id)


@router.post("/{goal_id}/record", response_model=GoalOut)
async def record_activity(
    goal_id: int, body: RecordBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.record_activity(db, goal_id, actor["org_id"], count=body.count)
    if not row:
        raise HTTPException(404, "Goal not found")
    return row


@router.post("/{goal_id}/reset", response_model=GoalOut)
async def reset_period(
    goal_id: int, body: ResetBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.reset_period(db, goal_id, actor["org_id"], body.new_period)
    if not row:
        raise HTTPException(404, "Goal not found")
    return row
