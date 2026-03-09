"""Deal risk scoring endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_roles
from app.core.deps import get_db
from app.services import deal_risk as svc

router = APIRouter(prefix="/deal-risks", tags=["deal-risks"])


class RiskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    deal_id: int
    risk_score: int
    risk_level: str
    factors_json: str
    scored_at: datetime


class RiskScore(BaseModel):
    deal_id: int
    risk_score: int
    factors: list[str] | None = None


@router.post("", response_model=RiskOut, status_code=201)
async def score_deal(
    data: RiskScore,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.score_deal(
        db, organization_id=actor["org_id"], **data.model_dump(),
    )


@router.get("", response_model=list[RiskOut])
async def list_risks(
    risk_level: str | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_risks(db, actor["org_id"], risk_level=risk_level)


@router.get("/summary")
async def get_summary(
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_risk_summary(db, actor["org_id"])


@router.get("/{deal_id}", response_model=RiskOut)
async def get_deal_risk(
    deal_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    risk = await svc.get_deal_risk(db, deal_id, actor["org_id"])
    if not risk:
        raise HTTPException(404, "Deal risk score not found")
    return risk
