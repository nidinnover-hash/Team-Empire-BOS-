"""Bulk action audit trail — detailed logging for bulk operations."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import bulk_action_log as bal_service

router = APIRouter(prefix="/bulk-action-logs", tags=["Bulk Action Logs"])


class BulkActionLogCreate(BaseModel):
    action_type: str = Field(..., max_length=50)
    entity_type: str = Field(..., max_length=30)
    total_records: int = Field(..., ge=0)
    success_count: int = Field(0, ge=0)
    failure_count: int = Field(0, ge=0)
    details: dict | None = None
    rollback_data: dict | None = None
    status: str = Field("completed", pattern=r"^(completed|partial|failed)$")


class BulkActionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    action_type: str
    entity_type: str
    total_records: int
    success_count: int
    failure_count: int
    details_json: str | None = None
    rollback_data_json: str | None = None
    status: str
    created_at: datetime | None = None


@router.get("", response_model=list[BulkActionLogRead])
async def list_bulk_action_logs(
    action_type: str | None = Query(None),
    entity_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[BulkActionLogRead]:
    items = await bal_service.list_bulk_actions(
        db, organization_id=actor["org_id"], action_type=action_type,
        entity_type=entity_type, limit=limit,
    )
    return [BulkActionLogRead.model_validate(log, from_attributes=True) for log in items]


@router.post("", response_model=BulkActionLogRead, status_code=201)
async def create_bulk_action_log(
    data: BulkActionLogCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> BulkActionLogRead:
    log = await bal_service.log_bulk_action(
        db, organization_id=actor["org_id"], user_id=int(actor["id"]),
        action_type=data.action_type, entity_type=data.entity_type,
        total_records=data.total_records, success_count=data.success_count,
        failure_count=data.failure_count, details=data.details,
        rollback_data=data.rollback_data, status=data.status,
    )
    return BulkActionLogRead.model_validate(log, from_attributes=True)


@router.get("/summary")
async def bulk_action_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await bal_service.get_bulk_action_summary(db, organization_id=actor["org_id"])


@router.get("/{log_id}", response_model=BulkActionLogRead)
async def get_bulk_action_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> BulkActionLogRead:
    log = await bal_service.get_bulk_action(db, log_id=log_id, organization_id=actor["org_id"])
    if log is None:
        raise HTTPException(status_code=404, detail="Bulk action log not found")
    return BulkActionLogRead.model_validate(log, from_attributes=True)
