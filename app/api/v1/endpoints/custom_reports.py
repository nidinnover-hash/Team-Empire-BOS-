"""Custom report builder endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import custom_report as svc

router = APIRouter(prefix="/custom-reports", tags=["custom-reports"])


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    description: str | None = None
    entity_type: str
    is_shared: bool
    created_by_user_id: int | None = None
    run_count: int
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReportCreate(BaseModel):
    name: str
    description: str | None = None
    entity_type: str = "deal"
    filters: dict | None = None
    grouping: list[str] | None = None
    aggregation: list[dict] | None = None
    columns: list[str] | None = None
    is_shared: bool = False


class ReportUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    filters: dict | None = None
    grouping: list[str] | None = None
    aggregation: list[dict] | None = None
    columns: list[str] | None = None
    is_shared: bool | None = None


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(
    body: ReportCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_report(db, organization_id=actor["org_id"], created_by_user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[ReportOut])
async def list_reports(
    entity_type: str | None = None,
    is_shared: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_reports(db, actor["org_id"], entity_type=entity_type, is_shared=is_shared)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_report(db, report_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Report not found")
    return row


@router.put("/{report_id}", response_model=ReportOut)
async def update_report(
    report_id: int,
    body: ReportUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_report(db, report_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Report not found")
    return row


@router.delete("/{report_id}", status_code=204)
async def delete_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_report(db, report_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Report not found")


@router.post("/{report_id}/run", response_model=ReportOut)
async def run_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.record_run(db, report_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Report not found")
    return row
