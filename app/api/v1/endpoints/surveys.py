"""CSAT survey endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import survey as svc

router = APIRouter(prefix="/surveys", tags=["surveys"])


class SurveyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    title: str
    description: str | None = None
    is_active: bool
    total_responses: int
    created_at: datetime
    updated_at: datetime


class SurveyCreate(BaseModel):
    title: str
    description: str | None = None
    questions: list[dict] | None = None
    is_active: bool = True


class SurveyUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    questions: list[dict] | None = None
    is_active: bool | None = None


class ResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    survey_id: int
    contact_id: int | None = None
    score: int
    nps_score: int | None = None
    feedback: str | None = None
    created_at: datetime


class ResponseCreate(BaseModel):
    score: int = 0
    nps_score: int | None = None
    contact_id: int | None = None
    answers: dict | None = None
    feedback: str | None = None


@router.post("", response_model=SurveyOut, status_code=201)
async def create_survey(
    body: SurveyCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_survey(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[SurveyOut])
async def list_surveys(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_surveys(db, actor["org_id"], is_active=is_active)


@router.get("/{survey_id}", response_model=SurveyOut)
async def get_survey(
    survey_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_survey(db, survey_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Survey not found")
    return row


@router.put("/{survey_id}", response_model=SurveyOut)
async def update_survey(
    survey_id: int,
    body: SurveyUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_survey(db, survey_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Survey not found")
    return row


@router.delete("/{survey_id}", status_code=204)
async def delete_survey(
    survey_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_survey(db, survey_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Survey not found")


@router.post("/{survey_id}/responses", response_model=ResponseOut, status_code=201)
async def submit_response(
    survey_id: int,
    body: ResponseCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.submit_response(db, organization_id=actor["org_id"], survey_id=survey_id, **body.model_dump())


@router.get("/{survey_id}/responses", response_model=list[ResponseOut])
async def list_responses(
    survey_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_responses(db, actor["org_id"], survey_id, limit=limit)


@router.get("/{survey_id}/nps")
async def get_nps(
    survey_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_nps(db, actor["org_id"], survey_id)
