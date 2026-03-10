"""Feedback / feature request endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import feature_request as svc

router = APIRouter(prefix="/feature-requests", tags=["feature-requests"])


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    title: str
    description: str | None = None
    category: str | None = None
    status: str
    priority: str
    votes: int
    submitted_by_user_id: int | None = None
    contact_id: int | None = None
    created_at: datetime
    updated_at: datetime


class RequestCreate(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    priority: str = "medium"
    contact_id: int | None = None


class RequestUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    status: str | None = None
    priority: str | None = None


@router.post("", response_model=RequestOut, status_code=201)
async def create_request(
    body: RequestCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_request(db, organization_id=actor["org_id"], submitted_by_user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[RequestOut])
async def list_requests(
    status: str | None = None, category: str | None = None,
    sort_by: str = "votes",
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_requests(db, actor["org_id"], status=status, category=category, sort_by=sort_by)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_stats(db, actor["org_id"])


@router.get("/{request_id}", response_model=RequestOut)
async def get_request(
    request_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_request(db, request_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Request not found")
    return row


@router.put("/{request_id}", response_model=RequestOut)
async def update_request(
    request_id: int, body: RequestUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_request(db, request_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Request not found")
    return row


@router.post("/{request_id}/vote", response_model=RequestOut)
async def vote(
    request_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.vote(db, request_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Request not found")
    return row
