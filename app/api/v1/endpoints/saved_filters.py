"""Saved filters — persist complex search queries with named presets."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import saved_filter as sf_service

router = APIRouter(prefix="/saved-filters", tags=["Saved Filters"])


class FilterCreate(BaseModel):
    name: str = Field(..., max_length=200)
    entity_type: str = Field(..., pattern=r"^(contact|deal|task)$")
    filters: dict = Field(default_factory=dict)
    is_shared: bool = False


class FilterUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    filters: dict | None = None
    is_shared: bool | None = None


class FilterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    entity_type: str
    filters_json: str
    is_shared: bool
    is_active: bool
    user_id: int
    created_at: datetime | None = None


@router.get("", response_model=list[FilterRead])
async def list_saved_filters(
    entity_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[FilterRead]:
    items = await sf_service.list_filters(
        db, organization_id=actor["org_id"], user_id=int(actor["id"]), entity_type=entity_type,
    )
    return [FilterRead.model_validate(f, from_attributes=True) for f in items]


@router.post("", response_model=FilterRead, status_code=201)
async def create_saved_filter(
    data: FilterCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> FilterRead:
    sf = await sf_service.create_filter(
        db, organization_id=actor["org_id"], user_id=int(actor["id"]),
        name=data.name, entity_type=data.entity_type,
        filters=data.filters, is_shared=data.is_shared,
    )
    return FilterRead.model_validate(sf, from_attributes=True)


@router.patch("/{filter_id}", response_model=FilterRead)
async def update_saved_filter(
    filter_id: int,
    data: FilterUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> FilterRead:
    sf = await sf_service.update_filter(
        db, filter_id=filter_id, organization_id=actor["org_id"],
        user_id=int(actor["id"]), **data.model_dump(exclude_unset=True),
    )
    if sf is None:
        raise HTTPException(status_code=404, detail="Filter not found")
    return FilterRead.model_validate(sf, from_attributes=True)


@router.delete("/{filter_id}", status_code=204)
async def delete_saved_filter(
    filter_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> None:
    deleted = await sf_service.delete_filter(
        db, filter_id=filter_id, organization_id=actor["org_id"], user_id=int(actor["id"]),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Filter not found")
