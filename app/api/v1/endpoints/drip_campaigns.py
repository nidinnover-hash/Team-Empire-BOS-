"""Email drip campaign endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import drip_campaign as svc

router = APIRouter(prefix="/drip-campaigns", tags=["drip-campaigns"])


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    description: str | None = None
    trigger_event: str | None = None
    is_active: bool
    total_enrolled: int
    total_completed: int
    total_unsubscribed: int
    created_at: datetime
    updated_at: datetime


class CampaignCreate(BaseModel):
    name: str
    description: str | None = None
    trigger_event: str | None = None
    is_active: bool = False


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_event: str | None = None
    is_active: bool | None = None


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    campaign_id: int
    step_order: int
    delay_days: int
    subject: str
    body: str
    created_at: datetime


class StepCreate(BaseModel):
    step_order: int = 0
    delay_days: int = 0
    subject: str = ""
    body: str = ""


class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    campaign_id: int
    contact_id: int
    current_step: int
    status: str
    enrolled_at: datetime
    completed_at: datetime | None = None


class EnrollBody(BaseModel):
    contact_id: int


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_campaign(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    is_active: bool | None = None, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_campaigns(db, actor["org_id"], is_active=is_active)


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_campaign(db, campaign_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Campaign not found")
    return row


@router.put("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: int, body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_campaign(db, campaign_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Campaign not found")
    return row


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_campaign(db, campaign_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Campaign not found")


@router.post("/{campaign_id}/steps", response_model=StepOut, status_code=201)
async def add_step(
    campaign_id: int, body: StepCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.add_step(db, organization_id=actor["org_id"], campaign_id=campaign_id, **body.model_dump())


@router.get("/{campaign_id}/steps", response_model=list[StepOut])
async def list_steps(
    campaign_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_steps(db, actor["org_id"], campaign_id)


@router.post("/{campaign_id}/enroll", response_model=EnrollmentOut, status_code=201)
async def enroll(
    campaign_id: int, body: EnrollBody,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.enroll(db, organization_id=actor["org_id"], campaign_id=campaign_id, contact_id=body.contact_id)


@router.get("/{campaign_id}/enrollments", response_model=list[EnrollmentOut])
async def list_enrollments(
    campaign_id: int, status: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_enrollments(db, actor["org_id"], campaign_id, status=status)


@router.post("/enrollments/{enrollment_id}/unsubscribe", response_model=EnrollmentOut)
async def unsubscribe(
    enrollment_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.unsubscribe(db, enrollment_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Enrollment not found")
    return row
