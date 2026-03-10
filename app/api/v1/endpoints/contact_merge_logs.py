"""Contact merge log endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import contact_merge_log as svc

router = APIRouter(prefix="/contact-merge-logs", tags=["contact-merge-logs"])


class MergeLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    primary_contact_id: int
    merged_contact_id: int
    merged_by_user_id: int
    before_snapshot: str | None = None
    after_snapshot: str | None = None
    fields_changed: str | None = None
    status: str
    created_at: datetime


class MergeLogCreate(BaseModel):
    primary_contact_id: int
    merged_contact_id: int
    before_snapshot: str | None = None
    after_snapshot: str | None = None
    fields_changed: str | None = None


@router.post("", response_model=MergeLogOut, status_code=201)
async def record_merge(
    body: MergeLogCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.record_merge(db, organization_id=actor["org_id"], merged_by_user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[MergeLogOut])
async def list_merges(
    contact_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_merges(db, actor["org_id"], contact_id=contact_id)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_stats(db, actor["org_id"])


@router.get("/{merge_id}", response_model=MergeLogOut)
async def get_merge(
    merge_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_merge(db, merge_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Merge log not found")
    return row
