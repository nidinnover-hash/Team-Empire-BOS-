"""Customer onboarding checklist endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import onboarding_checklist as svc

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TemplateCreate(BaseModel):
    name: str
    description: str | None = None
    steps: list[dict] | None = None
    is_active: bool = True


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict] | None = None
    is_active: bool | None = None


class ChecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    template_id: int
    contact_id: int | None = None
    deal_id: int | None = None
    status: str
    completed_steps: int
    total_steps: int
    assigned_user_id: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AssignBody(BaseModel):
    template_id: int
    contact_id: int | None = None
    deal_id: int | None = None
    assigned_user_id: int | None = None


class CompleteStepBody(BaseModel):
    step_index: int


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_template(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    is_active: bool | None = None, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_templates(db, actor["org_id"], is_active=is_active)


@router.get("/templates/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_template(db, template_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Template not found")
    return row


@router.put("/templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: int, body: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_template(db, template_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Template not found")
    return row


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_template(db, template_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Template not found")


@router.post("/checklists", response_model=ChecklistOut, status_code=201)
async def assign_checklist(
    body: AssignBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.assign_checklist(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("/checklists", response_model=list[ChecklistOut])
async def list_checklists(
    status: str | None = None, contact_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_checklists(db, actor["org_id"], status=status, contact_id=contact_id)


@router.get("/checklists/{checklist_id}", response_model=ChecklistOut)
async def get_checklist(
    checklist_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_checklist(db, checklist_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Checklist not found")
    return row


@router.post("/checklists/{checklist_id}/complete-step", response_model=ChecklistOut)
async def complete_step(
    checklist_id: int, body: CompleteStepBody,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.complete_step(db, checklist_id, actor["org_id"], body.step_index)
    if not row:
        raise HTTPException(404, "Checklist not found")
    return row
