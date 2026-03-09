"""Contact enrichment queue — batch enrichment request management."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import enrichment_queue as eq_service

router = APIRouter(prefix="/enrichment-queue", tags=["Enrichment Queue"])


class EnrichmentRequestCreate(BaseModel):
    contact_id: int
    source: str = Field("domain_lookup", max_length=50)


class EnrichmentBatchCreate(BaseModel):
    contact_ids: list[int] = Field(..., max_length=100)
    source: str = Field("domain_lookup", max_length=50)


class EnrichmentRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    status: str
    source: str
    result_json: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class EnrichmentComplete(BaseModel):
    result_data: dict | None = None
    error: str | None = None


@router.get("", response_model=list[EnrichmentRequestRead])
async def list_enrichment_queue(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[EnrichmentRequestRead]:
    items = await eq_service.list_queue(db, organization_id=actor["org_id"], status=status, limit=limit)
    return [EnrichmentRequestRead.model_validate(r, from_attributes=True) for r in items]


@router.post("", response_model=EnrichmentRequestRead, status_code=201)
async def enqueue_enrichment(
    data: EnrichmentRequestCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EnrichmentRequestRead:
    req = await eq_service.enqueue(
        db, organization_id=actor["org_id"], contact_id=data.contact_id,
        source=data.source, requested_by=int(actor["id"]),
    )
    return EnrichmentRequestRead.model_validate(req, from_attributes=True)


@router.post("/batch", response_model=list[EnrichmentRequestRead], status_code=201)
async def enqueue_batch(
    data: EnrichmentBatchCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[EnrichmentRequestRead]:
    reqs = await eq_service.enqueue_batch(
        db, organization_id=actor["org_id"], contact_ids=data.contact_ids,
        source=data.source, requested_by=int(actor["id"]),
    )
    return [EnrichmentRequestRead.model_validate(r, from_attributes=True) for r in reqs]


@router.patch("/{request_id}/complete", response_model=EnrichmentRequestRead)
async def complete_enrichment(
    request_id: int,
    data: EnrichmentComplete,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EnrichmentRequestRead:
    req = await eq_service.complete_enrichment(
        db, request_id=request_id, result_data=data.result_data, error=data.error,
    )
    if req is None:
        raise HTTPException(status_code=404, detail="Enrichment request not found")
    return EnrichmentRequestRead.model_validate(req, from_attributes=True)


@router.get("/stats")
async def enrichment_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await eq_service.get_enrichment_stats(db, organization_id=actor["org_id"])
