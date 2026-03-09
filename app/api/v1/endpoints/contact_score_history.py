"""Contact score history endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_roles
from app.core.deps import get_db
from app.services import contact_score_history as svc

router = APIRouter(prefix="/contact-scores", tags=["contact-scores"])


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; organization_id: int; contact_id: int
    score: int; previous_score: int | None = None
    change_reason: str | None = None; source: str
    details_json: str | None = None; created_at: datetime


class ScoreRecord(BaseModel):
    contact_id: int; score: int
    previous_score: int | None = None
    change_reason: str | None = None
    source: str = "manual"


@router.post("", response_model=ScoreOut, status_code=201)
async def record_score(
    data: ScoreRecord,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.record_score(db, organization_id=actor["org_id"], **data.model_dump())


@router.get("/{contact_id}", response_model=list[ScoreOut])
async def get_history(
    contact_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_history(db, actor["org_id"], contact_id)


@router.get("/{contact_id}/trend")
async def get_trend(
    contact_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_trend(db, actor["org_id"], contact_id)
