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
from app.services import money_approval_matrix as money_matrix_service
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


class RecordSendRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    contact_id: str = Field(..., min_length=1, max_length=255)
    channel: str = Field(..., max_length=50)


@router.post("/can-send", response_model=CanSendResponse)
async def can_send(
    data: CanSendRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> CanSendResponse:
    """BOS decides if a send is allowed. Other systems must call before sending."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    result = await contact_policy_service.can_send(
        db,
        data.organization_id,
        contact_id=data.contact_id,
        channel=data.channel,
        campaign_id=data.campaign_id,
    )
    return CanSendResponse(**result)


@router.post("/record-send", status_code=204)
async def record_send(
    data: RecordSendRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> None:
    """Call after a send so can_send rate limits work. Marketing app must call this after each send."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    await contact_policy_service.record_send(
        db,
        data.organization_id,
        contact_id=data.contact_id,
        channel=data.channel,
    )


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
    """Create a money approval in BOS. Auto-approve if actor role is in matrix for this amount band."""
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
    can_auto = await money_matrix_service.can_auto_approve_money(
        db,
        data.organization_id,
        action_type=data.action_type,
        amount=data.amount,
        actor_role=actor.get("role") or "STAFF",
    )
    if can_auto:
        approved = await approval_service.approve_approval(
            db,
            approval_id=approval.id,
            approver_id=actor["id"],
            organization_id=data.organization_id,
        )
        if approved:
            approval = approved
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


class MilestoneStep(BaseModel):
    step_key: str
    step_name: str
    deadline: str | None = None


class ApplicationMilestonesResponse(BaseModel):
    application_id: str
    steps: list[MilestoneStep]
    deadline: str | None = None


@router.post("/study-abroad/application-milestones", response_model=ApplicationMilestonesResponse)
async def application_milestones(
    data: ApplicationMilestonesRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ApplicationMilestonesResponse:
    """BOS returns next required steps for an application from milestone templates."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    result = await study_abroad_service.next_required_steps(
        db, data.organization_id, data.application_id
    )
    return ApplicationMilestonesResponse(
        application_id=result["application_id"],
        steps=[MilestoneStep(**s) for s in result["steps"]],
        deadline=result.get("deadline"),
    )


class RiskStatusRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    application_id: str = Field(..., min_length=1, max_length=255)


class RiskStatusResponse(BaseModel):
    application_id: str
    status: str  # on_track | at_risk | critical
    message: str | None = None
    critical_deadlines: list[str] = []


@router.post("/study-abroad/risk-status", response_model=RiskStatusResponse)
async def risk_status(
    data: RiskStatusRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> RiskStatusResponse:
    """BOS returns risk status from pending deadlines (on_track / at_risk / critical)."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    result = await study_abroad_service.risk_status(
        db, data.organization_id, data.application_id
    )
    return RiskStatusResponse(**result)
