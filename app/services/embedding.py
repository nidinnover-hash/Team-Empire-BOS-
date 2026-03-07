"""Embedding service — pgvector-backed semantic memory storage and retrieval."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING

from sqlalchemy import bindparam, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.memory_embedding import MemoryEmbedding

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
_embedding_bg_tasks: set[asyncio.Task[None]] = set()


# ── Text formatting ──────────────────────────────────────────────────────────

def format_embedding_text(source_type: str, **kwargs: str) -> str:
    """Format source data into a string suitable for embedding."""
    if source_type == "profile_memory":
        return f"{kwargs.get('key', '')}: {kwargs.get('value', '')}"
    if source_type == "daily_context":
        return f"[{kwargs.get('context_type', '')}] {kwargs.get('content', '')}"
    if source_type == "clone_memory":
        parts = [f"Situation: {kwargs.get('situation', '')}"]
        if kwargs.get("action_taken"):
            parts.append(f"Action: {kwargs['action_taken']}")
        if kwargs.get("outcome"):
            parts.append(f"Outcome: {kwargs['outcome']}")
        return "\n".join(parts)
    return str(kwargs.get("text", ""))


# ── Embedding generation ─────────────────────────────────────────────────────

async def generate_embedding(text_input: str) -> list[float] | None:
    """Generate an embedding vector using OpenAI. Returns None on any failure."""
    if not settings.EMBEDDING_ENABLED:
        return None
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key or api_key in {"", "sk-your-key-here", "sk-xxxxxxxxxxxxxxxxxxxxxxxx"}:
        logger.debug("Embedding skipped: no valid OPENAI_API_KEY")
        return None

    trimmed = text_input[:8000]  # OpenAI max ~8191 tokens for small model
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, timeout=settings.EMBEDDING_TIMEOUT_SECONDS)
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=trimmed,
        )
        return response.data[0].embedding
    except Exception:
        logger.warning("Embedding generation failed", exc_info=True)
        return None


# ── Storage ──────────────────────────────────────────────────────────────────

async def embed_memory(
    db: AsyncSession,
    organization_id: int,
    workspace_id: int | None,
    source_type: str,
    source_id: int,
    content_text: str,
) -> MemoryEmbedding | None:
    """Generate embedding and upsert into memory_embeddings table."""
    # pgvector requires PostgreSQL — skip on SQLite (tests)
    try:
        dialect = db.bind.dialect.name if db.bind else ""
    except Exception:
        dialect = ""
    if dialect == "sqlite":
        return None

    vector = await generate_embedding(content_text)
    if vector is None:
        return None

    # Check for existing row
    result = await db.execute(
        select(MemoryEmbedding).where(
            MemoryEmbedding.organization_id == organization_id,
            MemoryEmbedding.source_type == source_type,
            MemoryEmbedding.source_id == source_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.content_text = content_text
        existing.embedding = vector
        existing.workspace_id = workspace_id
        from datetime import UTC, datetime
        existing.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(existing)
        return existing

    row = MemoryEmbedding(
        organization_id=organization_id,
        workspace_id=workspace_id,
        source_type=source_type,
        source_id=source_id,
        content_text=content_text,
        embedding=vector,
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        logger.warning("embed_memory commit failed", exc_info=True)
        return None
    return row


async def embed_memory_background(
    organization_id: int,
    workspace_id: int | None,
    source_type: str,
    source_id: int,
    content_text: str,
) -> None:
    """Fire-and-forget embedding task. Opens its own DB session."""
    try:
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            await embed_memory(
                db, organization_id, workspace_id,
                source_type, source_id, content_text,
            )
    except Exception:
        logger.warning("Background embedding failed (org=%s, %s:%s)", organization_id, source_type, source_id, exc_info=True)


def schedule_embed(
    organization_id: int,
    workspace_id: int | None,
    source_type: str,
    source_id: int,
    content_text: str,
) -> None:
    """Schedule embedding as a fire-and-forget asyncio task. Safe to call from sync context."""
    if not settings.EMBEDDING_ENABLED:
        return
    # Skip on SQLite (tests) — pgvector requires PostgreSQL
    db_url = (settings.DATABASE_URL or "").strip().lower()
    if db_url.startswith("sqlite"):
        return
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(
            embed_memory_background(
                organization_id, workspace_id, source_type, source_id, content_text,
            )
        )
        _embedding_bg_tasks.add(task)
        task.add_done_callback(_embedding_bg_tasks.discard)
    except RuntimeError:
        logger.debug("No running event loop; skipping background embed")


# ── Retrieval ────────────────────────────────────────────────────────────────

async def backfill_embeddings(
    db: AsyncSession,
    organization_id: int,
    *,
    batch_size: int = 50,
    source_types: list[str] | None = None,
) -> dict[str, int]:
    """Backfill embeddings for historical memory data that doesn't have embeddings yet.

    Scans profile_memory, daily_context, and clone_memory tables and generates
    embeddings for any rows not yet in memory_embeddings.
    Returns counts per source_type.
    """
    if not settings.EMBEDDING_ENABLED:
        return {"skipped": 0, "reason": "EMBEDDING_ENABLED=false"}

    # pgvector requires PostgreSQL
    try:
        dialect = db.bind.dialect.name if db.bind else ""
    except Exception:
        dialect = ""
    if dialect == "sqlite":
        return {"skipped": 0, "reason": "sqlite"}

    types_to_process = source_types or ["profile_memory", "daily_context", "clone_memory"]
    counts: dict[str, int] = {}

    if "profile_memory" in types_to_process:
        counts["profile_memory"] = await _backfill_profile_memory(db, organization_id, batch_size)

    if "daily_context" in types_to_process:
        counts["daily_context"] = await _backfill_daily_context(db, organization_id, batch_size)

    if "clone_memory" in types_to_process:
        counts["clone_memory"] = await _backfill_clone_memory(db, organization_id, batch_size)

    return counts


async def _backfill_profile_memory(db: AsyncSession, org_id: int, batch_size: int) -> int:
    """Backfill embeddings for profile memory entries without embeddings."""
    from app.models.memory import ProfileMemory

    # Find profile memory IDs that don't have embeddings yet
    existing_ids_query = (
        select(MemoryEmbedding.source_id)
        .where(
            MemoryEmbedding.organization_id == org_id,
            MemoryEmbedding.source_type == "profile_memory",
        )
    )
    existing_result = await db.execute(existing_ids_query)
    existing_ids = {row[0] for row in existing_result.all()}

    entries_query = (
        select(ProfileMemory)
        .where(ProfileMemory.organization_id == org_id)
        .order_by(ProfileMemory.updated_at.desc())
        .limit(batch_size * 2)
    )
    entries = list((await db.execute(entries_query)).scalars().all())

    count = 0
    for entry in entries:
        if entry.id in existing_ids:
            continue
        if count >= batch_size:
            break
        text = format_embedding_text("profile_memory", key=entry.key, value=entry.value or "")
        result = await embed_memory(
            db, org_id, entry.workspace_id, "profile_memory", entry.id, text,
        )
        if result is not None:
            count += 1
    return count


async def _backfill_daily_context(db: AsyncSession, org_id: int, batch_size: int) -> int:
    """Backfill embeddings for daily context entries without embeddings."""
    from app.models.memory import DailyContext

    existing_ids_query = (
        select(MemoryEmbedding.source_id)
        .where(
            MemoryEmbedding.organization_id == org_id,
            MemoryEmbedding.source_type == "daily_context",
        )
    )
    existing_result = await db.execute(existing_ids_query)
    existing_ids = {row[0] for row in existing_result.all()}

    entries_query = (
        select(DailyContext)
        .where(DailyContext.organization_id == org_id)
        .order_by(DailyContext.created_at.desc())
        .limit(batch_size * 2)
    )
    entries = list((await db.execute(entries_query)).scalars().all())

    count = 0
    for entry in entries:
        if entry.id in existing_ids:
            continue
        if count >= batch_size:
            break
        text = format_embedding_text("daily_context", context_type=entry.context_type, content=entry.content or "")
        result = await embed_memory(
            db, org_id, entry.workspace_id, "daily_context", entry.id, text,
        )
        if result is not None:
            count += 1
    return count


async def _backfill_clone_memory(db: AsyncSession, org_id: int, batch_size: int) -> int:
    """Backfill embeddings for clone memory entries without embeddings."""
    from app.models.clone_memory import CloneMemoryEntry

    existing_ids_query = (
        select(MemoryEmbedding.source_id)
        .where(
            MemoryEmbedding.organization_id == org_id,
            MemoryEmbedding.source_type == "clone_memory",
        )
    )
    existing_result = await db.execute(existing_ids_query)
    existing_ids = {row[0] for row in existing_result.all()}

    entries_query = (
        select(CloneMemoryEntry)
        .where(CloneMemoryEntry.organization_id == org_id)
        .order_by(CloneMemoryEntry.updated_at.desc())
        .limit(batch_size * 2)
    )
    entries = list((await db.execute(entries_query)).scalars().all())

    count = 0
    for entry in entries:
        if entry.id in existing_ids:
            continue
        if count >= batch_size:
            break
        text = format_embedding_text(
            "clone_memory",
            situation=entry.situation or "",
            action_taken=entry.action_taken or "",
            outcome=entry.outcome or "",
        )
        result = await embed_memory(
            db, org_id, entry.workspace_id, "clone_memory", entry.id, text,
        )
        if result is not None:
            count += 1
    return count


async def search_similar(
    db: AsyncSession,
    organization_id: int,
    query_text: str,
    *,
    workspace_id: int | None = None,
    source_types: list[str] | None = None,
    limit: int | None = None,
    threshold: float | None = None,
) -> list[MemoryEmbedding]:
    """Find memory embeddings most similar to query_text using cosine distance."""
    if not settings.EMBEDDING_ENABLED:
        return []

    # pgvector requires PostgreSQL — skip on SQLite (tests)
    try:
        dialect = db.bind.dialect.name if db.bind else ""
    except Exception:
        dialect = ""
    if dialect == "sqlite":
        return []

    max_results = limit or settings.EMBEDDING_MAX_RESULTS
    min_threshold = threshold or settings.EMBEDDING_SIMILARITY_THRESHOLD

    query_vector = await generate_embedding(query_text)
    if query_vector is None:
        return []

    # Build raw SQL for pgvector cosine distance (<=>) operator
    vec_literal = "[" + ",".join(str(v) for v in query_vector) + "]"

    params: dict = {
        "org_id": organization_id,
        "limit": max_results,
        "threshold": min_threshold,
        "query_vector": vec_literal,
    }
    distance_expr = literal_column(
        "embedding <=> CAST(:query_vector AS vector)"
    ).label("distance")
    query = (
        select(
            MemoryEmbedding.id,
            MemoryEmbedding.organization_id,
            MemoryEmbedding.workspace_id,
            MemoryEmbedding.source_type,
            MemoryEmbedding.source_id,
            MemoryEmbedding.content_text,
            MemoryEmbedding.created_at,
            MemoryEmbedding.updated_at,
            distance_expr,
        )
        .where(MemoryEmbedding.organization_id == bindparam("org_id"))
        .where(distance_expr < (1.0 - bindparam("threshold")))
        .order_by(distance_expr.asc())
        .limit(bindparam("limit"))
    )

    if workspace_id is not None:
        query = query.where(MemoryEmbedding.workspace_id == bindparam("ws_id"))
        params["ws_id"] = workspace_id

    if source_types:
        query = query.where(MemoryEmbedding.source_type.in_(bindparam("source_types", expanding=True)))
        params["source_types"] = list(source_types)

    try:
        result = await db.execute(query, params)
        rows = result.mappings().all()
    except Exception:
        logger.warning("Semantic search failed (falling back to empty)", exc_info=True)
        # Rollback to clear the failed transaction state (e.g. SQLite doesn't support pgvector)
        with suppress(Exception):
            await db.rollback()
        return []

    # Reconstruct lightweight MemoryEmbedding-like objects from raw rows
    embeddings: list[MemoryEmbedding] = []
    for row in rows:
        obj = MemoryEmbedding(
            id=row["id"],
            organization_id=row["organization_id"],
            workspace_id=row["workspace_id"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            content_text=row["content_text"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        embeddings.append(obj)
    return embeddings
