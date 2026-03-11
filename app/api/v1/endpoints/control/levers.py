"""Control levers — can_send, route_lead, money approval, study abroad. Other systems call BOS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_helpers import record_critical_mutation
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.approval import ApprovalRequestCreate
from app.services import approval as approval_service
from app.services import contact_policy as contact_policy_service
from app.services import lead_routing_service as lead_routing_service
from app.services import study_abroad as study_abroad_service

router = APIRouter(prefix="/levers", tags=["Control Levers"])


# ── can_send ─────────────────────────────────────────────────────────────────


class CanSendRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    contact_id: str = Field(..., min_length=1, max_length=255)
    channel: str = Field(..., max_length=50)
    campaign_id: str | None = Field(None, max_length=255)


class CanSendResponse(BaseModel):
    allowed: bool
    reason: str | None
    recommended_time_utc: str | None


@router.post("/can-send", response_model=CanSendResponse)
async def can_send(
    data: CanSendRequest,
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> CanSendResponse:
    """BOS decides if a send is allowed. Other systems must call before sending."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    result = await contact_policy_service.can_send(
        data.organization_id,
        contact_id=data.contact_id,
        channel=data.channel,
        campaign_id=data.campaign_id,
    )
    return CanSendResponse(**result)


# ── route_lead ───────────────────────────────────────────────────────────────


class RouteLeadRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    lead_type: str = Field(default="general", max_length=50)
    region: str | None = Field(None, max_length=100)
    source: str | None = Field(None, max_length=100)
    payload: dict | None = None


class RouteLeadResponse(BaseModel):
    owner_user_id: int | None
    owner_email: str | None
    queue_id: int | None
    sla_deadline_utc: str | None
    allowed: bool
    reason: str | None


@router.post("/route-lead", response_model=RouteLeadResponse)
async def route_lead(
    data: RouteLeadRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> RouteLeadResponse:
    """BOS assigns owner and SLA for a new lead. Other systems must call before assigning."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    result = await lead_routing_service.route_lead(
        db,
        data.organization_id,
        lead_type=data.lead_type,
        region=data.region,
        source=data.source,
        payload=data.payload,
    )
    return RouteLeadResponse(**result)


# ── request_money_approval ───────────────────────────────────────────────────


class RequestMoneyApprovalRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    action_type: str = Field(..., max_length=50)
    amount: float = Field(..., ge=0)
    currency: str = Field(default="USD", max_length=10)
    payload: dict | None = None


class RequestMoneyApprovalResponse(BaseModel):
    approval_id: int
    status: str


@router.post("/request-money-approval", response_model=RequestMoneyApprovalResponse)
async def request_money_approval(
    data: RequestMoneyApprovalRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> RequestMoneyApprovalResponse:
    """Create a money approval in BOS. No money action without BOS approval_id."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    payload_json = {
        "action_type": data.action_type,
        "amount": data.amount,
        "currency": data.currency,
        **(data.payload or {}),
    }
    create = ApprovalRequestCreate(
        organization_id=data.organization_id,
        approval_type=f"money_{data.action_type}",
        payload_json=payload_json,
    )
    approval = await approval_service.request_approval(db, int(actor["id"]), create)
    await record_critical_mutation(
        db,
        event_type="money_approval_requested",
        organization_id=data.organization_id,
        actor_user_id=actor["id"],
        entity_type="approval",
        entity_id=approval.id,
        payload_json={"action_type": data.action_type, "amount": data.amount},
    )
    return RequestMoneyApprovalResponse(approval_id=approval.id, status=approval.status)


# ── Study abroad (ESA) ───────────────────────────────────────────────────────


class ApplicationMilestonesRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    application_id: str = Field(..., min_length=1, max_length=255)


@router.post("/study-abroad/application-milestones")
async def application_milestones(
    data: ApplicationMilestonesRequest,
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
):
    """BOS returns next required steps for an application. Stub returns empty for now."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    return await study_abroad_service.next_required_steps(
        data.organization_id, data.application_id
    )


class RiskStatusRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    application_id: str = Field(..., min_length=1, max_length=255)


@router.post("/study-abroad/risk-status")
async def risk_status(
    data: RiskStatusRequest,
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
):
    """BOS returns risk status for an application. Stub returns on_track."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    return await study_abroad_service.risk_status(
        data.organization_id, data.application_id
    )
