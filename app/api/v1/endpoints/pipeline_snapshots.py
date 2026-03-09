"""Pipeline snapshot endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_roles
from app.core.deps import get_db
from app.services import pipeline_snapshot as svc

router = APIRouter(prefix="/pipeline-snapshots", tags=["pipeline-snapshots"])


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    snapshot_type: str
    total_deals: int
    total_value: int
    stage_breakdown_json: str
    weighted_value: int
    new_deals: int
    won_deals: int
    lost_deals: int
    created_at: datetime


class SnapshotCreate(BaseModel):
    snapshot_type: str = "daily"
    total_deals: int = 0
    total_value: int = 0
    stage_breakdown: dict | None = None
    weighted_value: int = 0
    new_deals: int = 0
    won_deals: int = 0
    lost_deals: int = 0


@router.post("", response_model=SnapshotOut, status_code=201)
async def create_snapshot(
    data: SnapshotCreate,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_snapshot(
        db, organization_id=actor["org_id"], **data.model_dump(),
    )


@router.get("", response_model=list[SnapshotOut])
async def list_snapshots(
    snapshot_type: str | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_snapshots(db, actor["org_id"], snapshot_type=snapshot_type)


@router.get("/trend")
async def get_trend(
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_trend(db, actor["org_id"])


@router.get("/{snapshot_id}", response_model=SnapshotOut)
async def get_snapshot(
    snapshot_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    snap = await svc.get_snapshot(db, snapshot_id, actor["org_id"])
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    return snap
