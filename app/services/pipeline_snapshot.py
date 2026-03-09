"""Pipeline snapshot service — periodic state captures."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline_snapshot import PipelineSnapshot


async def create_snapshot(
    db: AsyncSession, *, organization_id: int,
    snapshot_type: str = "daily", total_deals: int = 0, total_value: int = 0,
    stage_breakdown: dict | None = None, weighted_value: int = 0,
    new_deals: int = 0, won_deals: int = 0, lost_deals: int = 0,
) -> PipelineSnapshot:
    row = PipelineSnapshot(
        organization_id=organization_id, snapshot_type=snapshot_type,
        total_deals=total_deals, total_value=total_value,
        stage_breakdown_json=json.dumps(stage_breakdown or {}),
        weighted_value=weighted_value,
        new_deals=new_deals, won_deals=won_deals, lost_deals=lost_deals,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_snapshots(
    db: AsyncSession, organization_id: int, *,
    snapshot_type: str | None = None, limit: int = 30,
) -> list[PipelineSnapshot]:
    q = select(PipelineSnapshot).where(PipelineSnapshot.organization_id == organization_id)
    if snapshot_type:
        q = q.where(PipelineSnapshot.snapshot_type == snapshot_type)
    q = q.order_by(PipelineSnapshot.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_snapshot(db: AsyncSession, snapshot_id: int, organization_id: int) -> PipelineSnapshot | None:
    q = select(PipelineSnapshot).where(
        PipelineSnapshot.id == snapshot_id,
        PipelineSnapshot.organization_id == organization_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def get_trend(db: AsyncSession, organization_id: int, *, limit: int = 14) -> list[dict]:
    snapshots = await list_snapshots(db, organization_id, snapshot_type="daily", limit=limit)
    return [
        {
            "date": s.created_at.isoformat() if s.created_at else None,
            "total_deals": s.total_deals,
            "total_value": s.total_value,
            "weighted_value": s.weighted_value,
            "won_deals": s.won_deals,
            "lost_deals": s.lost_deals,
        }
        for s in reversed(snapshots)
    ]
