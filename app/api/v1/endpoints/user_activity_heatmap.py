"""User activity heatmap endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import user_activity_heatmap as svc

router = APIRouter(prefix="/user-activity", tags=["user-activity"])


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    user_id: int
    activity_type: str
    feature_name: str | None = None
    hour_of_day: int
    day_of_week: int
    created_at: datetime


class ActivityCreate(BaseModel):
    activity_type: str
    hour_of_day: int
    day_of_week: int
    feature_name: str | None = None


@router.post("", response_model=ActivityOut, status_code=201)
async def record_activity(
    data: ActivityCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.record_activity(
        db, organization_id=actor["org_id"],
        user_id=actor["id"], **data.model_dump(),
    )


@router.get("", response_model=list[ActivityOut])
async def list_activities(
    user_id: int | None = None,
    activity_type: str | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_activities(
        db, actor["org_id"], user_id=user_id, activity_type=activity_type,
    )


@router.get("/heatmap")
async def get_heatmap(
    user_id: int | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_heatmap(db, actor["org_id"], user_id=user_id)


@router.get("/top-features")
async def get_top_features(
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_top_features(db, actor["org_id"])
