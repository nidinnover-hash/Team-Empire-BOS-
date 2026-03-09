"""Contact enrichment queue service."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enrichment_queue import EnrichmentRequest


async def enqueue(
    db: AsyncSession, organization_id: int, contact_id: int,
    source: str = "domain_lookup", requested_by: int | None = None,
) -> EnrichmentRequest:
    req = EnrichmentRequest(
        organization_id=organization_id, contact_id=contact_id,
        source=source, requested_by_user_id=requested_by,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def enqueue_batch(
    db: AsyncSession, organization_id: int, contact_ids: list[int],
    source: str = "domain_lookup", requested_by: int | None = None,
) -> list[EnrichmentRequest]:
    reqs = []
    for cid in contact_ids[:100]:
        req = EnrichmentRequest(
            organization_id=organization_id, contact_id=cid,
            source=source, requested_by_user_id=requested_by,
        )
        db.add(req)
        reqs.append(req)
    await db.commit()
    for r in reqs:
        await db.refresh(r)
    return reqs


async def list_queue(
    db: AsyncSession, organization_id: int, status: str | None = None, limit: int = 50,
) -> list[EnrichmentRequest]:
    q = select(EnrichmentRequest).where(EnrichmentRequest.organization_id == organization_id)
    if status:
        q = q.where(EnrichmentRequest.status == status)
    result = await db.execute(q.order_by(EnrichmentRequest.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def complete_enrichment(
    db: AsyncSession, request_id: int, result_data: dict | None = None, error: str | None = None,
) -> EnrichmentRequest | None:
    result = await db.execute(select(EnrichmentRequest).where(EnrichmentRequest.id == request_id))
    req = result.scalar_one_or_none()
    if not req:
        return None
    if error:
        req.status = "failed"
        req.error_message = error
    else:
        req.status = "completed"
        req.result_json = json.dumps(result_data) if result_data else None
    req.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(req)
    return req


async def get_enrichment_stats(db: AsyncSession, organization_id: int) -> dict:
    items = await list_queue(db, organization_id, limit=1000)
    by_status: dict[str, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    return {"total": len(items), "by_status": by_status}
