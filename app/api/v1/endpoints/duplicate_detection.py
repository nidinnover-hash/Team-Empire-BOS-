"""Duplicate detection — find and manage potential duplicate contacts/deals."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import duplicate_detection as dup_service

router = APIRouter(prefix="/duplicates", tags=["Duplicate Detection"])


class DuplicateMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_a_id: int
    entity_b_id: int
    match_score: int
    match_fields: str
    status: str
    resolved_by_user_id: int | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None


class ResolveRequest(BaseModel):
    status: str = Field(..., pattern=r"^(merged|dismissed)$")


@router.get("/scan/contacts")
async def scan_contact_duplicates(
    threshold: int = Query(60, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    matches = await dup_service.scan_contact_duplicates(db, organization_id=actor["org_id"], threshold=threshold)
    return {"total_matches": len(matches), "matches": matches}


@router.get("", response_model=list[DuplicateMatchRead])
async def list_duplicate_matches(
    entity_type: str | None = Query(None),
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[DuplicateMatchRead]:
    items = await dup_service.list_duplicate_matches(
        db, organization_id=actor["org_id"], entity_type=entity_type, status=status, limit=limit,
    )
    return [DuplicateMatchRead.model_validate(m, from_attributes=True) for m in items]


@router.patch("/{match_id}/resolve", response_model=DuplicateMatchRead)
async def resolve_duplicate(
    match_id: int,
    data: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DuplicateMatchRead:
    match = await dup_service.resolve_duplicate(
        db, match_id=match_id, organization_id=actor["org_id"],
        status=data.status, user_id=int(actor["id"]),
    )
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return DuplicateMatchRead.model_validate(match, from_attributes=True)
