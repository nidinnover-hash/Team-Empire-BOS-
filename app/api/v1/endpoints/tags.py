"""Tag management — centralized tags with merge and usage tracking."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import tag_management as tag_service

router = APIRouter(prefix="/tags", tags=["Tags"])


class TagCreate(BaseModel):
    name: str = Field(..., max_length=100)
    color: str = Field("#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")


class TagUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    usage_count: int
    created_at: datetime | None = None


class TagMergeRequest(BaseModel):
    source_tag_id: int
    target_tag_id: int


@router.get("", response_model=list[TagRead])
async def list_tags(
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[TagRead]:
    items = await tag_service.list_tags(db, organization_id=actor["org_id"], search=search)
    return [TagRead.model_validate(t, from_attributes=True) for t in items]


@router.post("", response_model=TagRead, status_code=201)
async def create_tag(
    data: TagCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TagRead:
    tag = await tag_service.create_tag(db, organization_id=actor["org_id"], name=data.name, color=data.color)
    return TagRead.model_validate(tag, from_attributes=True)


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: int,
    data: TagUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TagRead:
    tag = await tag_service.update_tag(
        db, tag_id=tag_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return TagRead.model_validate(tag, from_attributes=True)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await tag_service.delete_tag(db, tag_id=tag_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found")


@router.post("/merge", response_model=TagRead)
async def merge_tags(
    data: TagMergeRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TagRead:
    tag = await tag_service.merge_tags(
        db, organization_id=actor["org_id"],
        source_tag_id=data.source_tag_id, target_tag_id=data.target_tag_id,
    )
    if tag is None:
        raise HTTPException(status_code=404, detail="One or both tags not found")
    return TagRead.model_validate(tag, from_attributes=True)
