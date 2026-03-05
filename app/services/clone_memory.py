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
    workspace_id: int | None = None,
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
        workspace_id=workspace_id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    from app.services.embedding import format_embedding_text, schedule_embed
    schedule_embed(
        org_id, entry.workspace_id,
        "clone_memory", entry.id,
        format_embedding_text("clone_memory", situation=situation, action_taken=action_taken, outcome=outcome),
    )
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
    workspace_id: int | None = None,
) -> list[CloneMemoryEntry]:
    """Retrieve memories similar to a given situation. Tries semantic search first, falls back to ILIKE."""
    from app.core.config import settings as _settings

    if _settings.EMBEDDING_ENABLED:
        try:
            from app.services.embedding import search_similar

            sem_results = await search_similar(
                db, org_id, situation_query,
                workspace_id=workspace_id, source_types=["clone_memory"], limit=limit,
            )
            if sem_results:
                ids = [r.source_id for r in sem_results]
                q = select(CloneMemoryEntry).where(
                    CloneMemoryEntry.id.in_(ids),
                    CloneMemoryEntry.employee_id == employee_id,
                    CloneMemoryEntry.confidence >= min_confidence,
                )
                if category:
                    q = q.where(CloneMemoryEntry.category == category)
                if outcome_filter:
                    q = q.where(CloneMemoryEntry.outcome == outcome_filter)
                result = await db.execute(q)
                memories = list(result.scalars().all())
                if memories:
                    # Update last_retrieved_at
                    hit_ids = [m.id for m in memories]
                    await db.execute(
                        update(CloneMemoryEntry)
                        .where(CloneMemoryEntry.id.in_(hit_ids))
                        .values(last_retrieved_at=datetime.now(UTC))
                    )
                    await db.commit()
                    return memories
        except Exception:
            logger.debug("Semantic retrieve_similar failed, falling back to ILIKE", exc_info=True)

    # Fallback: keyword-based ILIKE
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
    if workspace_id is not None:
        query = query.where(CloneMemoryEntry.workspace_id == workspace_id)
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
    *,
    workspace_id: int | None = None,
) -> int:
    """Decay confidence of memories not retrieved recently."""
    cutoff = datetime.now(UTC) - timedelta(days=days_since_retrieval)
    _filters = [
        CloneMemoryEntry.organization_id == org_id,
        CloneMemoryEntry.confidence > 0.1,
        (
            (CloneMemoryEntry.last_retrieved_at.is_(None))
            | (CloneMemoryEntry.last_retrieved_at < cutoff)
        ),
    ]
    if workspace_id is not None:
        _filters.append(CloneMemoryEntry.workspace_id == workspace_id)
    result = await db.execute(select(CloneMemoryEntry).where(*_filters))
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
    *,
    workspace_id: int | None = None,
) -> dict:
    """Get memory bank statistics."""
    from sqlalchemy import func

    base_filters = [CloneMemoryEntry.organization_id == org_id]
    if workspace_id is not None:
        base_filters.append(CloneMemoryEntry.workspace_id == workspace_id)
    if employee_id:
        base_filters.append(CloneMemoryEntry.employee_id == employee_id)

    query = select(
        func.count(CloneMemoryEntry.id).label("total"),
        func.avg(CloneMemoryEntry.confidence).label("avg_confidence"),
        func.sum(CloneMemoryEntry.reinforcement_count).label("total_reinforcements"),
    ).where(*base_filters)

    result = await db.execute(query)
    row = result.one()

    # Category breakdown
    cat_query = select(
        CloneMemoryEntry.category,
        func.count(CloneMemoryEntry.id),
    ).where(*base_filters)
    cat_result = await db.execute(cat_query.group_by(CloneMemoryEntry.category))
    categories = {cat: count for cat, count in cat_result.all()}

    # Outcome breakdown
    out_query = select(
        CloneMemoryEntry.outcome,
        func.count(CloneMemoryEntry.id),
    ).where(*base_filters)
    out_result = await db.execute(out_query.group_by(CloneMemoryEntry.outcome))
    outcomes = {outcome: count for outcome, count in out_result.all()}

    return {
        "total_memories": row.total or 0,
        "avg_confidence": round(float(row.avg_confidence or 0), 3),
        "total_reinforcements": int(row.total_reinforcements or 0),
        "by_category": categories,
        "by_outcome": outcomes,
    }
