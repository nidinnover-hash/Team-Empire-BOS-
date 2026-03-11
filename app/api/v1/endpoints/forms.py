"""Form builder endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import form_builder as svc

router = APIRouter(prefix="/forms", tags=["forms"])


class FormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    description: str | None = None
    fields_json: str
    redirect_url: str | None = None
    confirmation_message: str | None = None
    is_active: bool
    total_submissions: int
    created_by_user_id: int | None = None
    created_at: datetime


class FormCreate(BaseModel):
    name: str
    description: str | None = None
    fields: list[dict] | None = None
    redirect_url: str | None = None
    confirmation_message: str | None = None


class FormUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    fields: list[dict] | None = None
    is_active: bool | None = None


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    form_id: int
    organization_id: int
    data_json: str
    contact_id: int | None = None
    source_ip: str | None = None
    created_at: datetime


class SubmitData(BaseModel):
    data: dict
    contact_id: int | None = None


@router.post("", response_model=FormOut, status_code=201)
async def create_form(
    data: FormCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_form(
        db, organization_id=actor["org_id"],
        created_by_user_id=actor["id"], **data.model_dump(),
    )


@router.get("", response_model=list[FormOut])
async def list_forms(
    is_active: bool | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_forms(db, actor["org_id"], is_active=is_active)


@router.get("/{form_id}", response_model=FormOut)
async def get_form(
    form_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.get_form(db, form_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Form not found")
    return row


@router.patch("/{form_id}", response_model=FormOut)
async def update_form(
    form_id: int, data: FormUpdate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.update_form(db, form_id, actor["org_id"], **data.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Form not found")
    return row


@router.delete("/{form_id}", status_code=204)
async def delete_form(
    form_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.delete_form(db, form_id, actor["org_id"]):
        raise HTTPException(404, "Form not found")


@router.post("/{form_id}/submit", response_model=SubmissionOut, status_code=201)
async def submit_form(
    form_id: int, data: SubmitData,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.submit_form(
        db, form_id=form_id, organization_id=actor["org_id"],
        data=data.data, contact_id=data.contact_id,
    )


@router.get("/{form_id}/submissions", response_model=list[SubmissionOut])
async def list_submissions(
    form_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_submissions(db, form_id, actor["org_id"])
