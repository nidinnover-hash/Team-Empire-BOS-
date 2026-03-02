"""Clone memory — stores and retrieves interaction patterns for RAG-lite learning."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clone_memory import CloneMemoryEntry

logger = logging.getLogger(__name__)


async def store_memory(
    db: AsyncSession,
    org_id: int,
    employee_id: int,
    situation: str,
    action_taken: str,
    outcome: str,
    *,
    outcome_detail: str | None = None,
    category: str = "general",
    tags: str | None = None,
    confidence: float = 0.7,
    source_type: str | None = None,
    source_id: int | None = None,
) -> CloneMemoryEntry:
    """Store a new memory entry for a clone."""
    entry = CloneMemoryEntry(
        organization_id=org_id,
        employee_id=employee_id,
        situation=situation,
        action_taken=action_taken,
        outcome=outcome,
        outcome_detail=outcome_detail,
        category=category,
        tags=tags,
        confidence=confidence,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def retrieve_similar(
    db: AsyncSession,
    org_id: int,
    employee_id: int,
    situation_query: str,
    *,
    category: str | None = None,
    outcome_filter: str | None = None,
    limit: int = 5,
    min_confidence: float = 0.3,
) -> list[CloneMemoryEntry]:
    """Retrieve memories similar to a given situation (keyword-based)."""
    pattern = f"%{situation_query}%"
    query = select(CloneMemoryEntry).where(
        CloneMemoryEntry.organization_id == org_id,
        CloneMemoryEntry.employee_id == employee_id,
        CloneMemoryEntry.confidence >= min_confidence,
        (
            CloneMemoryEntry.situation.ilike(pattern)
            | CloneMemoryEntry.tags.ilike(pattern)
            | CloneMemoryEntry.action_taken.ilike(pattern)
        ),
    )
    if category:
        query = query.where(CloneMemoryEntry.category == category)
    if outcome_filter:
        query = query.where(CloneMemoryEntry.outcome == outcome_filter)
    query = query.order_by(
        CloneMemoryEntry.confidence.desc(),
        CloneMemoryEntry.reinforcement_count.desc(),
    ).limit(limit)

    result = await db.execute(query)
    memories = list(result.scalars().all())

    # Update last_retrieved_at for retrieved memories
    if memories:
        ids = [m.id for m in memories]
        await db.execute(
            update(CloneMemoryEntry)
            .where(CloneMemoryEntry.id.in_(ids))
            .values(last_retrieved_at=datetime.now(UTC))
        )
        await db.commit()

    return memories


async def reinforce_memory(
    db: AsyncSession,
    org_id: int,
    memory_id: int,
    confidence_boost: float = 0.05,
) -> CloneMemoryEntry | None:
    """Reinforce a memory — increase confidence when it leads to a good outcome."""
    result = await db.execute(
        select(CloneMemoryEntry).where(
            CloneMemoryEntry.id == memory_id,
            CloneMemoryEntry.organization_id == org_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return None
    entry.confidence = min(1.0, entry.confidence + confidence_boost)
    entry.reinforcement_count += 1
    entry.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(entry)
    return entry


async def decay_old_memories(
    db: AsyncSession,
    org_id: int,
    days_since_retrieval: int = 90,
    decay_amount: float = 0.05,
) -> int:
    """Decay confidence of memories not retrieved recently."""
    cutoff = datetime.now(UTC) - timedelta(days=days_since_retrieval)
    result = await db.execute(
        select(CloneMemoryEntry).where(
            CloneMemoryEntry.organization_id == org_id,
            CloneMemoryEntry.confidence > 0.1,
            (
                (CloneMemoryEntry.last_retrieved_at.is_(None))
                | (CloneMemoryEntry.last_retrieved_at < cutoff)
            ),
        )
    )
    entries = list(result.scalars().all())
    count = 0
    for entry in entries:
        entry.confidence = max(0.1, entry.confidence - decay_amount)
        count += 1
    if count > 0:
        await db.commit()
    return count


async def get_memory_stats(
    db: AsyncSession,
    org_id: int,
    employee_id: int | None = None,
) -> dict:
    """Get memory bank statistics."""
    from sqlalchemy import func

    query = select(
        func.count(CloneMemoryEntry.id).label("total"),
        func.avg(CloneMemoryEntry.confidence).label("avg_confidence"),
        func.sum(CloneMemoryEntry.reinforcement_count).label("total_reinforcements"),
    ).where(CloneMemoryEntry.organization_id == org_id)

    if employee_id:
        query = query.where(CloneMemoryEntry.employee_id == employee_id)

    result = await db.execute(query)
    row = result.one()

    # Category breakdown
    cat_query = select(
        CloneMemoryEntry.category,
        func.count(CloneMemoryEntry.id),
    ).where(CloneMemoryEntry.organization_id == org_id)
    if employee_id:
        cat_query = cat_query.where(CloneMemoryEntry.employee_id == employee_id)
    cat_result = await db.execute(cat_query.group_by(CloneMemoryEntry.category))
    categories = {cat: count for cat, count in cat_result.all()}

    # Outcome breakdown
    out_query = select(
        CloneMemoryEntry.outcome,
        func.count(CloneMemoryEntry.id),
    ).where(CloneMemoryEntry.organization_id == org_id)
    if employee_id:
        out_query = out_query.where(CloneMemoryEntry.employee_id == employee_id)
    out_result = await db.execute(out_query.group_by(CloneMemoryEntry.outcome))
    outcomes = {outcome: count for outcome, count in out_result.all()}

    return {
        "total_memories": row.total or 0,
        "avg_confidence": round(float(row.avg_confidence or 0), 3),
        "total_reinforcements": int(row.total_reinforcements or 0),
        "by_category": categories,
        "by_outcome": outcomes,
    }
