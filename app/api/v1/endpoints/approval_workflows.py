"""Approval workflows — configurable multi-step approval chains."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import approval_workflow as wf_service

router = APIRouter(prefix="/approval-workflows", tags=["Approval Workflows"])


class WorkflowCreate(BaseModel):
    name: str = Field(..., max_length=200)
    entity_type: str = Field(..., max_length=50)
    trigger_condition: str = Field(..., max_length=200)


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    entity_type: str
    trigger_condition: str
    is_active: bool
    created_at: datetime | None = None


class StepCreate(BaseModel):
    step_order: int = Field(1, ge=1)
    approver_role: str = Field(..., max_length=30)
    approver_user_id: int | None = None
    escalation_hours: int = Field(24, ge=1)


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    step_order: int
    approver_role: str
    approver_user_id: int | None = None
    escalation_hours: int
    created_at: datetime | None = None


@router.get("", response_model=list[WorkflowRead])
async def list_approval_workflows(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[WorkflowRead]:
    items = await wf_service.list_workflows(db, organization_id=actor["org_id"], active_only=active_only)
    return [WorkflowRead.model_validate(w, from_attributes=True) for w in items]


@router.post("", response_model=WorkflowRead, status_code=201)
async def create_approval_workflow(
    data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkflowRead:
    wf = await wf_service.create_workflow(
        db, organization_id=actor["org_id"],
        name=data.name, entity_type=data.entity_type,
        trigger_condition=data.trigger_condition,
    )
    return WorkflowRead.model_validate(wf, from_attributes=True)


@router.delete("/{workflow_id}", status_code=204)
async def delete_approval_workflow(
    workflow_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await wf_service.delete_workflow(db, workflow_id=workflow_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.get("/{workflow_id}")
async def get_workflow_detail(
    workflow_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    result = await wf_service.get_workflow_with_steps(db, workflow_id=workflow_id, organization_id=actor["org_id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return result


@router.post("/{workflow_id}/steps", response_model=StepRead, status_code=201)
async def add_workflow_step(
    workflow_id: int,
    data: StepCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> StepRead:
    step = await wf_service.add_step(
        db, workflow_id=workflow_id,
        step_order=data.step_order, approver_role=data.approver_role,
        approver_user_id=data.approver_user_id, escalation_hours=data.escalation_hours,
    )
    return StepRead.model_validate(step, from_attributes=True)


@router.get("/{workflow_id}/steps", response_model=list[StepRead])
async def list_workflow_steps(
    workflow_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[StepRead]:
    items = await wf_service.list_steps(db, workflow_id=workflow_id)
    return [StepRead.model_validate(s, from_attributes=True) for s in items]
