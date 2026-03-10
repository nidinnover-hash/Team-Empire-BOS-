"""Competitor tracking endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import competitor as svc

router = APIRouter(prefix="/competitors", tags=["competitors"])


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    website: str | None = None
    strengths: str | None = None
    weaknesses: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class CompetitorCreate(BaseModel):
    name: str
    website: str | None = None
    strengths: str | None = None
    weaknesses: str | None = None
    notes: str | None = None


class CompetitorUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    strengths: str | None = None
    weaknesses: str | None = None
    notes: str | None = None


class DealCompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    deal_id: int
    competitor_id: int
    threat_level: str
    win_loss_reason: str | None = None
    created_at: datetime


class DealCompetitorCreate(BaseModel):
    deal_id: int
    competitor_id: int
    threat_level: str = "medium"
    win_loss_reason: str | None = None


@router.post("", response_model=CompetitorOut, status_code=201)
async def create_competitor(
    body: CompetitorCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_competitor(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[CompetitorOut])
async def list_competitors(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_competitors(db, actor["org_id"])


@router.get("/win-loss-stats")
async def get_win_loss_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_win_loss_stats(db, actor["org_id"])


@router.get("/{competitor_id}", response_model=CompetitorOut)
async def get_competitor(
    competitor_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_competitor(db, competitor_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Competitor not found")
    return row


@router.put("/{competitor_id}", response_model=CompetitorOut)
async def update_competitor(
    competitor_id: int,
    body: CompetitorUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_competitor(db, competitor_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Competitor not found")
    return row


@router.delete("/{competitor_id}", status_code=204)
async def delete_competitor(
    competitor_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_competitor(db, competitor_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Competitor not found")


@router.post("/deal-link", response_model=DealCompetitorOut, status_code=201)
async def link_competitor_to_deal(
    body: DealCompetitorCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.link_to_deal(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("/deals/{deal_id}", response_model=list[DealCompetitorOut])
async def list_deal_competitors(
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_deal_competitors(db, actor["org_id"], deal_id)
