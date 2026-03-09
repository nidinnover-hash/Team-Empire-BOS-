"""Email template library — reusable templates with variable substitution."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import email_template as tmpl_service

router = APIRouter(prefix="/email-templates", tags=["Email Templates"])


class EmailTemplateCreate(BaseModel):
    name: str = Field(..., max_length=200)
    subject: str = Field(..., max_length=500)
    body: str
    category: str = Field("general", max_length=50)
    variables: list[str] | None = None


class EmailTemplateUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    subject: str | None = None
    body: str | None = None
    category: str | None = None
    variables: list[str] | None = None


class EmailTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    subject: str
    body: str
    category: str
    variables_json: str | None = None
    is_active: bool
    created_at: datetime | None = None


class RenderRequest(BaseModel):
    variables: dict[str, str] = {}


@router.get("", response_model=list[EmailTemplateRead])
async def list_email_templates(
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[EmailTemplateRead]:
    items = await tmpl_service.list_templates(db, organization_id=actor["org_id"], category=category)
    return [EmailTemplateRead.model_validate(t, from_attributes=True) for t in items]


@router.post("", response_model=EmailTemplateRead, status_code=201)
async def create_email_template(
    data: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EmailTemplateRead:
    tmpl = await tmpl_service.create_template(
        db, organization_id=actor["org_id"], created_by_user_id=int(actor["id"]),
        name=data.name, subject=data.subject, body=data.body,
        category=data.category, variables=data.variables,
    )
    return EmailTemplateRead.model_validate(tmpl, from_attributes=True)


@router.get("/{template_id}", response_model=EmailTemplateRead)
async def get_email_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmailTemplateRead:
    tmpl = await tmpl_service.get_template(db, template_id=template_id, organization_id=actor["org_id"])
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return EmailTemplateRead.model_validate(tmpl, from_attributes=True)


@router.patch("/{template_id}", response_model=EmailTemplateRead)
async def update_email_template(
    template_id: int,
    data: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EmailTemplateRead:
    tmpl = await tmpl_service.update_template(
        db, template_id=template_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return EmailTemplateRead.model_validate(tmpl, from_attributes=True)


@router.delete("/{template_id}", status_code=204)
async def delete_email_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await tmpl_service.delete_template(db, template_id=template_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")


@router.post("/{template_id}/render")
async def render_email_template(
    template_id: int,
    data: RenderRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Render a template with variable substitution."""
    tmpl = await tmpl_service.get_template(db, template_id=template_id, organization_id=actor["org_id"])
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpl_service.render_template(tmpl.body, tmpl.subject, data.variables)
