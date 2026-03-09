"""Document template endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_roles
from app.core.deps import get_db
from app.services import document_template as svc

router = APIRouter(prefix="/document-templates", tags=["document-templates"])


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    doc_type: str
    content: str
    merge_fields_json: str
    version: int
    is_active: bool
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class TemplateCreate(BaseModel):
    name: str
    doc_type: str
    content: str
    merge_fields: list[str] | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    doc_type: str | None = None
    content: str | None = None
    merge_fields: list[str] | None = None
    is_active: bool | None = None


class RenderRequest(BaseModel):
    data: dict


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    data: TemplateCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_template(
        db, organization_id=actor["org_id"],
        created_by_user_id=actor["id"], **data.model_dump(),
    )


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    doc_type: str | None = None,
    is_active: bool | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_templates(db, actor["org_id"], doc_type=doc_type, is_active=is_active)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.get_template(db, template_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Template not found")
    return row


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.update_template(
        db, template_id, actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if not row:
        raise HTTPException(404, "Template not found")
    return row


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.delete_template(db, template_id, actor["org_id"]):
        raise HTTPException(404, "Template not found")


@router.post("/{template_id}/render")
async def render_template(
    template_id: int,
    data: RenderRequest,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    result = await svc.render_template(db, template_id, actor["org_id"], data.data)
    if result is None:
        raise HTTPException(404, "Template not found")
    return result
