"""Referral program endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import referral as svc

router = APIRouter(prefix="/referrals", tags=["referrals"])


class ReferralSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    tracking_code: str
    reward_type: str
    reward_value: float
    total_referrals: int
    total_conversions: int
    total_rewards_paid: float
    notes: str | None = None
    created_at: datetime


class ReferralSourceCreate(BaseModel):
    name: str
    tracking_code: str
    reward_type: str = "flat"
    reward_value: float = 0.0
    notes: str | None = None


class ReferralOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    source_id: int
    contact_id: int | None = None
    deal_id: int | None = None
    status: str
    reward_amount: float
    created_at: datetime


class ReferralCreate(BaseModel):
    source_id: int
    contact_id: int | None = None
    deal_id: int | None = None


class ConvertBody(BaseModel):
    reward_amount: float = 0.0


@router.post("/sources", response_model=ReferralSourceOut, status_code=201)
async def create_source(
    body: ReferralSourceCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_source(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("/sources", response_model=list[ReferralSourceOut])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_sources(db, actor["org_id"])


@router.get("/sources/{source_id}", response_model=ReferralSourceOut)
async def get_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_source(db, source_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Referral source not found")
    return row


@router.post("", response_model=ReferralOut, status_code=201)
async def create_referral(
    body: ReferralCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_referral(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[ReferralOut])
async def list_referrals(
    source_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_referrals(db, actor["org_id"], source_id=source_id, status=status, limit=limit)


@router.post("/{referral_id}/convert", response_model=ReferralOut)
async def convert_referral(
    referral_id: int,
    body: ConvertBody,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.convert_referral(db, referral_id, actor["org_id"], reward_amount=body.reward_amount)
    if not row:
        raise HTTPException(404, "Referral not found")
    return row


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_stats(db, actor["org_id"])
