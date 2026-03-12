"""Recurring report schedule endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import report_schedule as schedule_service

router = APIRouter(prefix="/reports/schedules", tags=["Report Schedules"])


class ReportScheduleCreate(BaseModel):
    name: str = Field(..., max_length=200)
    report_type: str = Field(..., pattern=r"^(kpi_summary|deal_pipeline|task_status|finance_summary)$")
    frequency: str = Field(..., pattern=r"^(daily|weekly|monthly)$")
    recipients: list[str] = Field(..., min_length=1, max_length=20)


class ReportScheduleUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    frequency: str | None = Field(None, pattern=r"^(daily|weekly|monthly)$")
    recipients: list[str] | None = None
    is_active: bool | None = None


class ReportScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    report_type: str
    frequency: str
    recipients_json: str
    is_active: bool
    last_sent_at: datetime | None = None
    created_at: datetime | None = None


@router.get("", response_model=list[ReportScheduleRead])
async def list_report_schedules(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[ReportScheduleRead]:
    items = await schedule_service.list_schedules(db, organization_id=actor["org_id"], active_only=active_only)
    return [ReportScheduleRead.model_validate(s, from_attributes=True) for s in items]


@router.post("", response_model=ReportScheduleRead, status_code=201)
async def create_report_schedule(
    data: ReportScheduleCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ReportScheduleRead:
    schedule = await schedule_service.create_schedule(
        db, organization_id=actor["org_id"], created_by_user_id=int(actor["id"]),
        name=data.name, report_type=data.report_type, frequency=data.frequency,
        recipients=data.recipients,
    )
    return ReportScheduleRead.model_validate(schedule, from_attributes=True)


@router.patch("/{schedule_id}", response_model=ReportScheduleRead)
async def update_report_schedule(
    schedule_id: int,
    data: ReportScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ReportScheduleRead:
    kwargs = data.model_dump(exclude_unset=True)
    schedule = await schedule_service.update_schedule(
        db, schedule_id=schedule_id, organization_id=actor["org_id"], **kwargs,
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return ReportScheduleRead.model_validate(schedule, from_attributes=True)


@router.delete("/{schedule_id}", status_code=204)
async def delete_report_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await schedule_service.delete_schedule(db, schedule_id=schedule_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
