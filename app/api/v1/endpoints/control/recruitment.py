"""Recruitment control — route candidates and ownership (EmpireO). Used by the Recruitment App."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_helpers import record_critical_mutation
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.platform.signals import publish_signal
from app.platform.signals.models import SignalCategory, SignalEnvelope
from app.platform.signals.topics import RECRUITMENT_PLACEMENT_CONFIRMED
from app.services import recruitment_routing as routing_service

router = APIRouter(prefix="/recruitment", tags=["Recruitment Control"])


class RouteCandidateRequest(BaseModel):
    """Request body for POST /control/recruitment/route-candidate."""

    organization_id: int = Field(..., ge=1)
    candidate_id: str = Field(..., min_length=1, max_length=255)
    job_id: str | None = Field(None, max_length=255)
    source: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    product_line: str | None = Field(None, max_length=100)


class RouteCandidateResponse(BaseModel):
    """Response for POST /control/recruitment/route-candidate."""

    owner_user_id: int | None
    owner_email: str | None
    queue_id: int | None
    sla_first_contact_at: str | None
    allowed: bool
    reason: str | None


@router.post("/route-candidate", response_model=RouteCandidateResponse)
async def route_candidate(
    data: RouteCandidateRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> RouteCandidateResponse:
    """
    BOS assigns owner and SLA for a new candidate. The Recruitment App must call
    this when a candidate is created and use the returned owner_user_id and
    sla_first_contact_at. No routing logic in the app — BOS controls it.
    """
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")

    result = await routing_service.route_candidate(
        db,
        data.organization_id,
        candidate_id=data.candidate_id,
        job_id=data.job_id,
        source=data.source,
        region=data.region,
        product_line=data.product_line,
    )
    return RouteCandidateResponse(**result)


# ── Assign owner ─────────────────────────────────────────────────────────────


class AssignOwnerRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    candidate_id: str = Field(..., min_length=1, max_length=255)
    job_id: str | None = Field(None, max_length=255)
    new_owner_user_id: int = Field(..., ge=1)
    reason: str | None = Field(None, max_length=500)


class AssignOwnerResponse(BaseModel):
    allowed: bool
    previous_owner_user_id: int | None
    new_owner_user_id: int
    message: str | None


@router.post("/assign-owner", response_model=AssignOwnerResponse)
async def assign_owner(
    data: AssignOwnerRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> AssignOwnerResponse:
    """BOS allows or denies ownership change. Recruitment App must call before reassigning."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    result = await routing_service.assign_owner(
        db,
        data.organization_id,
        candidate_id=data.candidate_id,
        job_id=data.job_id,
        new_owner_user_id=data.new_owner_user_id,
        reason=data.reason,
    )
    return AssignOwnerResponse(**result)


# ── Candidate stage ──────────────────────────────────────────────────────────


class CandidateStageRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    candidate_id: str = Field(..., min_length=1, max_length=255)
    job_id: str | None = Field(None, max_length=255)
    from_stage: str = Field(..., max_length=100)
    to_stage: str = Field(..., max_length=100)
    payload: dict | None = None


class CandidateStageResponse(BaseModel):
    allowed: bool
    requires_approval: bool
    approval_type: str | None
    message: str | None


@router.post("/candidate-stage", response_model=CandidateStageResponse)
async def candidate_stage(
    data: CandidateStageRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> CandidateStageResponse:
    """BOS allows or denies stage change; may require approval (e.g. before Offer)."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    result = await routing_service.candidate_stage(
        db,
        data.organization_id,
        candidate_id=data.candidate_id,
        job_id=data.job_id,
        from_stage=data.from_stage,
        to_stage=data.to_stage,
        payload=data.payload,
    )
    return CandidateStageResponse(**result)


# ── Confirm placement ────────────────────────────────────────────────────────


class ConfirmPlacementRequest(BaseModel):
    organization_id: int = Field(..., ge=1)
    candidate_id: str = Field(..., min_length=1, max_length=255)
    job_id: str | None = Field(None, max_length=255)
    approval_id: int | None = Field(None, ge=1)
    placed_at: str | None = Field(None, max_length=50)
    start_date: str | None = Field(None, max_length=50)
    payload: dict | None = None


class ConfirmPlacementResponse(BaseModel):
    recorded: bool
    placement_id: str


@router.post("/confirm-placement", response_model=ConfirmPlacementResponse)
async def confirm_placement(
    data: ConfirmPlacementRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ConfirmPlacementResponse:
    """BOS records placement for audit. Recruitment App calls after placement confirmed."""
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    result = await routing_service.confirm_placement(
        db,
        data.organization_id,
        candidate_id=data.candidate_id,
        job_id=data.job_id,
        approval_id=data.approval_id,
        placed_at=data.placed_at,
        start_date=data.start_date,
        payload=data.payload,
    )
    await record_critical_mutation(
        db,
        event_type="placement_confirmed",
        organization_id=data.organization_id,
        actor_user_id=actor["id"],
        entity_type="recruitment_placement",
        payload_json={
            "placement_id": result["placement_id"],
            "candidate_id": data.candidate_id,
            "job_id": data.job_id,
        },
    )
    await publish_signal(
        SignalEnvelope(
            topic=RECRUITMENT_PLACEMENT_CONFIRMED,
            category=SignalCategory.DECISION,
            organization_id=data.organization_id,
            actor_user_id=actor["id"],
            source="control.recruitment",
            entity_type="recruitment_placement",
            entity_id=result["placement_id"],
            payload={
                "placement_id": result["placement_id"],
                "candidate_id": data.candidate_id,
                "job_id": data.job_id,
            },
        ),
        db=db,
    )
    return ConfirmPlacementResponse(**result)
