"""SLA policies — response/resolution time targets with breach tracking."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import sla_policy as sla_service

router = APIRouter(prefix="/sla-policies", tags=["SLA Policies"])


class SlaPolicyCreate(BaseModel):
    name: str = Field(..., max_length=200)
    entity_type: str = Field(..., pattern=r"^(deal|task)$")
    target_field: str = Field(..., max_length=50)
    target_value: str = Field(..., max_length=50)
    response_hours: int | None = None
    resolution_hours: int | None = None


class SlaPolicyUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    response_hours: int | None = None
    resolution_hours: int | None = None
    is_active: bool | None = None


class SlaPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    entity_type: str
    target_field: str
    target_value: str
    response_hours: int | None = None
    resolution_hours: int | None = None
    is_active: bool
    created_at: datetime | None = None


class SlaBreachRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    policy_id: int
    entity_type: str
    entity_id: int
    breach_type: str
    breached_at: datetime | None = None
    resolved_at: datetime | None = None


@router.get("", response_model=list[SlaPolicyRead])
async def list_sla_policies(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[SlaPolicyRead]:
    items = await sla_service.list_policies(db, organization_id=actor["org_id"], active_only=active_only)
    return [SlaPolicyRead.model_validate(p, from_attributes=True) for p in items]


@router.post("", response_model=SlaPolicyRead, status_code=201)
async def create_sla_policy(
    data: SlaPolicyCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SlaPolicyRead:
    policy = await sla_service.create_policy(
        db, organization_id=actor["org_id"],
        name=data.name, entity_type=data.entity_type,
        target_field=data.target_field, target_value=data.target_value,
        response_hours=data.response_hours, resolution_hours=data.resolution_hours,
    )
    return SlaPolicyRead.model_validate(policy, from_attributes=True)


@router.patch("/{policy_id}", response_model=SlaPolicyRead)
async def update_sla_policy(
    policy_id: int,
    data: SlaPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SlaPolicyRead:
    policy = await sla_service.update_policy(
        db, policy_id=policy_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="SLA policy not found")
    return SlaPolicyRead.model_validate(policy, from_attributes=True)


@router.delete("/{policy_id}", status_code=204)
async def delete_sla_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await sla_service.delete_policy(db, policy_id=policy_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="SLA policy not found")


@router.get("/breaches", response_model=list[SlaBreachRead])
async def list_sla_breaches(
    entity_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[SlaBreachRead]:
    items = await sla_service.list_breaches(db, organization_id=actor["org_id"], entity_type=entity_type, limit=limit)
    return [SlaBreachRead.model_validate(b, from_attributes=True) for b in items]


@router.post("/breaches", response_model=SlaBreachRead, status_code=201)
async def record_sla_breach(
    policy_id: int = Query(...),
    entity_type: str = Query(...),
    entity_id: int = Query(...),
    breach_type: str = Query(..., pattern=r"^(response|resolution)$"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SlaBreachRead:
    breach = await sla_service.record_breach(
        db, organization_id=actor["org_id"], policy_id=policy_id,
        entity_type=entity_type, entity_id=entity_id, breach_type=breach_type,
    )
    return SlaBreachRead.model_validate(breach, from_attributes=True)


@router.get("/check")
async def check_entity_sla(
    entity_type: str = Query(...),
    target_field: str = Query(...),
    target_value: str = Query(...),
    created_at: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return {
        "violations": await sla_service.check_entity_sla(
            db, organization_id=actor["org_id"], entity_type=entity_type,
            target_field=target_field, target_value=target_value, created_at=created_at,
        )
    }
