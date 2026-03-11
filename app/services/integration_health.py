"""Integration Health Dashboard — unified health overview for all connected integrations."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import Integration


async def get_integration_health_summary(
    db: AsyncSession,
    organization_id: int,
) -> dict:
    """Overall health: total connected, healthy, degraded, error counts."""
    rows = (
        await db.execute(
            select(Integration).where(
                Integration.organization_id == organization_id,
            )
        )
    ).scalars().all()

    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(hours=24)

    total = len(rows)
    connected = 0
    healthy = 0
    degraded = 0
    errored = 0
    disconnected = 0
    never_synced = 0

    for r in rows:
        if r.status != "connected":
            disconnected += 1
            continue
        connected += 1
        if r.last_sync_status == "error" or r.sync_error_count >= 3:
            errored += 1
        elif r.last_sync_at is None:
            never_synced += 1
        else:
            sync_at = r.last_sync_at.replace(tzinfo=UTC) if r.last_sync_at.tzinfo is None else r.last_sync_at
            if sync_at < stale_cutoff:
                degraded += 1
            else:
                healthy += 1

    return {
        "total": total,
        "connected": connected,
        "healthy": healthy,
        "degraded": degraded,
        "errored": errored,
        "disconnected": disconnected,
        "never_synced": never_synced,
        "health_score": round(healthy / connected, 4) if connected > 0 else 0.0,
    }


async def get_integration_details(
    db: AsyncSession,
    organization_id: int,
) -> list[dict]:
    """Per-integration health details."""
    rows = (
        await db.execute(
            select(Integration)
            .where(Integration.organization_id == organization_id)
            .order_by(Integration.type)
        )
    ).scalars().all()

    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(hours=24)
    results = []

    for r in rows:
        if r.status != "connected":
            health = "disconnected"
        elif r.last_sync_status == "error" or r.sync_error_count >= 3:
            health = "error"
        elif r.last_sync_at is None:
            health = "never_synced"
        else:
            sync_at = r.last_sync_at.replace(tzinfo=UTC) if r.last_sync_at.tzinfo is None else r.last_sync_at
            health = "degraded" if sync_at < stale_cutoff else "healthy"

        age_hours = None
        if r.last_sync_at:
            sync_at_tz = r.last_sync_at.replace(tzinfo=UTC) if r.last_sync_at.tzinfo is None else r.last_sync_at
            age_hours = round((now - sync_at_tz).total_seconds() / 3600, 1)

        results.append({
            "id": r.id,
            "type": r.type,
            "status": r.status,
            "health": health,
            "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
            "last_sync_status": r.last_sync_status,
            "sync_error_count": r.sync_error_count,
            "age_hours": age_hours,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return results


async def get_full_integration_health(
    db: AsyncSession,
    organization_id: int,
) -> dict:
    """Combined summary + details for the health dashboard."""
    summary = await get_integration_health_summary(db, organization_id)
    details = await get_integration_details(db, organization_id)
    return {
        "summary": summary,
        "integrations": details,
    }
