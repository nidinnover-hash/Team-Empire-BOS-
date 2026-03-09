"""Email campaign endpoints — CRUD for drip campaigns, steps, and enrollments."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.services import campaign_analytics as analytics_service
from app.services import email_campaign as campaign_service

router = APIRouter(prefix="/campaigns", tags=["Email Campaigns"])


class CampaignCreate(BaseModel):
    name: str = Field(..., max_length=300)
    description: str | None = None


class CampaignStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(draft|active|paused|completed)$")


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    status: str
    created_at: datetime | None = None


class StepCreate(BaseModel):
    subject: str = Field(..., max_length=500)
    body_template: str
    step_order: int = 1
    delay_hours: int = Field(24, ge=1, le=720)


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    step_order: int
    subject: str
    body_template: str
    delay_hours: int


class EnrollRequest(BaseModel):
    contact_id: int


class EnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    contact_id: int
    current_step: int
    status: str
    next_send_at: datetime | None = None
    enrolled_at: datetime | None = None


@router.post("", response_model=CampaignRead, status_code=201)
async def create_campaign(
    data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CampaignRead:
    campaign = await campaign_service.create_campaign(
        db, organization_id=actor["org_id"],
        name=data.name, description=data.description,
        created_by_user_id=int(actor["id"]),
    )
    await record_action(
        db, event_type="campaign_created", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="campaign", entity_id=campaign.id,
        payload_json={"name": data.name},
    )
    return CampaignRead.model_validate(campaign, from_attributes=True)


@router.get("", response_model=list[CampaignRead])
async def list_campaigns(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[CampaignRead]:
    items = await campaign_service.list_campaigns(db, organization_id=actor["org_id"], status=status)
    return [CampaignRead.model_validate(c, from_attributes=True) for c in items]


@router.get("/{campaign_id}/summary")
async def campaign_summary(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    result = await campaign_service.get_campaign_summary(db, actor["org_id"], campaign_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return result


@router.patch("/{campaign_id}/status", response_model=CampaignRead)
async def update_status(
    campaign_id: int,
    data: CampaignStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CampaignRead:
    campaign = await campaign_service.update_campaign_status(
        db, organization_id=actor["org_id"], campaign_id=campaign_id, status=data.status,
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignRead.model_validate(campaign, from_attributes=True)


@router.post("/{campaign_id}/steps", response_model=StepRead, status_code=201)
async def add_step(
    campaign_id: int,
    data: StepCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> StepRead:
    campaign = await campaign_service.get_campaign(db, actor["org_id"], campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    step = await campaign_service.add_step(
        db, campaign_id=campaign_id, subject=data.subject,
        body_template=data.body_template, step_order=data.step_order,
        delay_hours=data.delay_hours,
    )
    return StepRead.model_validate(step, from_attributes=True)


@router.get("/{campaign_id}/steps", response_model=list[StepRead])
async def list_steps(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[StepRead]:
    steps = await campaign_service.list_steps(db, campaign_id=campaign_id)
    return [StepRead.model_validate(s, from_attributes=True) for s in steps]


@router.post("/{campaign_id}/enroll", response_model=EnrollmentRead, status_code=201)
async def enroll_contact(
    campaign_id: int,
    data: EnrollRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EnrollmentRead:
    campaign = await campaign_service.get_campaign(db, actor["org_id"], campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    enrollment = await campaign_service.enroll_contact(db, campaign_id=campaign_id, contact_id=data.contact_id)
    return EnrollmentRead.model_validate(enrollment, from_attributes=True)


@router.get("/{campaign_id}/enrollments", response_model=list[EnrollmentRead])
async def list_enrollments(
    campaign_id: int,
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[EnrollmentRead]:
    items = await campaign_service.list_enrollments(db, campaign_id=campaign_id, status=status)
    return [EnrollmentRead.model_validate(e, from_attributes=True) for e in items]


# ---------------------------------------------------------------------------
# Campaign analytics & A/B tracking
# ---------------------------------------------------------------------------


class CampaignEventCreate(BaseModel):
    event_type: str = Field(..., pattern=r"^(sent|opened|clicked|bounced|unsubscribed)$")
    step_id: int | None = None
    enrollment_id: int | None = None
    contact_id: int | None = None
    variant: str | None = Field(None, pattern=r"^[AB]$")


@router.post("/{campaign_id}/events", status_code=201)
async def record_campaign_event(
    campaign_id: int,
    data: CampaignEventCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    event = await analytics_service.record_event(
        db, organization_id=actor["org_id"], campaign_id=campaign_id,
        event_type=data.event_type, step_id=data.step_id,
        enrollment_id=data.enrollment_id, contact_id=data.contact_id,
        variant=data.variant,
    )
    return {"id": event.id, "event_type": event.event_type, "created_at": event.created_at.isoformat()}


@router.get("/{campaign_id}/analytics")
async def get_campaign_analytics(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await analytics_service.get_campaign_analytics(
        db, organization_id=actor["org_id"], campaign_id=campaign_id,
    )
