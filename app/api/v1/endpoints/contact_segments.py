"""Contact segments — saved filter queries for dynamic contact grouping."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import contact_segment as segment_service

router = APIRouter(prefix="/contact-segments", tags=["Contact Segments"])


class SegmentCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = None
    filters: dict = Field(default_factory=dict)


class SegmentUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    filters: dict | None = None


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    filters_json: str
    is_active: bool
    created_at: datetime | None = None


@router.get("", response_model=list[SegmentRead])
async def list_segments(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[SegmentRead]:
    items = await segment_service.list_segments(db, organization_id=actor["org_id"])
    return [SegmentRead.model_validate(s, from_attributes=True) for s in items]


@router.post("", response_model=SegmentRead, status_code=201)
async def create_segment(
    data: SegmentCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SegmentRead:
    segment = await segment_service.create_segment(
        db, organization_id=actor["org_id"], created_by_user_id=int(actor["id"]),
        name=data.name, description=data.description, filters=data.filters,
    )
    return SegmentRead.model_validate(segment, from_attributes=True)


@router.patch("/{segment_id}", response_model=SegmentRead)
async def update_segment(
    segment_id: int,
    data: SegmentUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SegmentRead:
    segment = await segment_service.update_segment(
        db, segment_id=segment_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    return SegmentRead.model_validate(segment, from_attributes=True)


@router.delete("/{segment_id}", status_code=204)
async def delete_segment(
    segment_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await segment_service.delete_segment(db, segment_id=segment_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Segment not found")


@router.get("/{segment_id}/evaluate")
async def evaluate_segment(
    segment_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Evaluate a segment's filters and return matching contacts."""
    result = await segment_service.evaluate_segment(
        db, segment_id=segment_id, organization_id=actor["org_id"], limit=limit,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
