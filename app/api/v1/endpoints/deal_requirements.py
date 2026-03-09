"""Deal stage requirements — checklists that must be completed before advancing."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import deal_stage_requirement as req_service

router = APIRouter(prefix="/deals/requirements", tags=["Deal Stage Requirements"])


class RequirementCreate(BaseModel):
    stage: str = Field(..., pattern=r"^(discovery|proposal|negotiation|contract|won|lost)$")
    title: str = Field(..., max_length=300)
    description: str | None = None
    is_mandatory: bool = True
    sort_order: int = 0


class RequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage: str
    title: str
    description: str | None = None
    is_mandatory: bool
    sort_order: int
    is_active: bool
    created_at: datetime | None = None


class CheckRequest(BaseModel):
    notes: str | None = None


@router.get("", response_model=list[RequirementRead])
async def list_requirements(
    stage: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[RequirementRead]:
    items = await req_service.list_requirements(db, organization_id=actor["org_id"], stage=stage)
    return [RequirementRead.model_validate(r, from_attributes=True) for r in items]


@router.post("", response_model=RequirementRead, status_code=201)
async def create_requirement(
    data: RequirementCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RequirementRead:
    req = await req_service.create_requirement(
        db, organization_id=actor["org_id"],
        stage=data.stage, title=data.title, description=data.description,
        is_mandatory=data.is_mandatory, sort_order=data.sort_order,
    )
    return RequirementRead.model_validate(req, from_attributes=True)


@router.delete("/{req_id}", status_code=204)
async def delete_requirement(
    req_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await req_service.delete_requirement(db, req_id=req_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Requirement not found")


@router.post("/{req_id}/check/{deal_id}")
async def check_requirement(
    req_id: int,
    deal_id: int,
    data: CheckRequest | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Mark a requirement as completed for a deal."""
    check = await req_service.check_requirement(
        db, deal_id=deal_id, requirement_id=req_id,
        user_id=int(actor["id"]), notes=data.notes if data else None,
    )
    return {
        "id": check.id, "deal_id": check.deal_id,
        "requirement_id": check.requirement_id,
        "is_completed": check.is_completed,
    }


@router.get("/checklist/{deal_id}/{stage}")
async def get_deal_checklist(
    deal_id: int,
    stage: str,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    return await req_service.get_deal_checklist(db, deal_id=deal_id, stage=stage, organization_id=actor["org_id"])


@router.get("/validate/{deal_id}/{stage}")
async def validate_stage_entry(
    deal_id: int,
    stage: str,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Check if a deal meets all mandatory requirements for a stage."""
    return await req_service.validate_stage_entry(db, deal_id=deal_id, stage=stage, organization_id=actor["org_id"])
