"""Data retention policies — configurable auto-archive/purge rules."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import data_retention as dr_service

router = APIRouter(prefix="/data-retention", tags=["Data Retention"])


class RetentionPolicyCreate(BaseModel):
    entity_type: str = Field(..., pattern=r"^(contact|deal|task|event)$")
    action: str = Field("archive", pattern=r"^(archive|purge)$")
    retention_days: int = Field(365, ge=1)
    condition_field: str | None = None
    condition_value: str | None = None


class RetentionPolicyUpdate(BaseModel):
    retention_days: int | None = Field(None, ge=1)
    action: str | None = Field(None, pattern=r"^(archive|purge)$")
    is_active: bool | None = None


class RetentionPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    action: str
    retention_days: int
    condition_field: str | None = None
    condition_value: str | None = None
    last_run_at: datetime | None = None
    records_affected: int
    is_active: bool
    created_at: datetime | None = None


@router.get("", response_model=list[RetentionPolicyRead])
async def list_retention_policies(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[RetentionPolicyRead]:
    items = await dr_service.list_policies(db, organization_id=actor["org_id"], active_only=active_only)
    return [RetentionPolicyRead.model_validate(p, from_attributes=True) for p in items]


@router.post("", response_model=RetentionPolicyRead, status_code=201)
async def create_retention_policy(
    data: RetentionPolicyCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RetentionPolicyRead:
    policy = await dr_service.create_policy(
        db, organization_id=actor["org_id"], **data.model_dump(),
    )
    return RetentionPolicyRead.model_validate(policy, from_attributes=True)


@router.patch("/{policy_id}", response_model=RetentionPolicyRead)
async def update_retention_policy(
    policy_id: int,
    data: RetentionPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RetentionPolicyRead:
    policy = await dr_service.update_policy(
        db, policy_id=policy_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return RetentionPolicyRead.model_validate(policy, from_attributes=True)


@router.delete("/{policy_id}", status_code=204)
async def delete_retention_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await dr_service.delete_policy(db, policy_id=policy_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy not found")


@router.get("/{policy_id}/evaluate")
async def evaluate_retention_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    result = await dr_service.evaluate_policy(db, policy_id=policy_id, organization_id=actor["org_id"])
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
