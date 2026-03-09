"""Job queue handlers — register all background job handlers here.

This module is imported at startup to populate the handler registry.
Each handler is an async function that receives keyword arguments from the job payload.
"""
from __future__ import annotations

import logging

from app.services.job_queue import handler

logger = logging.getLogger(__name__)


@handler("embed_memory")
async def handle_embed_memory(
    organization_id: int,
    workspace_id: int | None = None,
    source_type: str = "",
    source_id: int = 0,
    content_text: str = "",
) -> None:
    """Generate and store an embedding for a memory entry."""
    from app.services.embedding import embed_memory_background
    await embed_memory_background(
        organization_id, workspace_id, source_type, source_id, content_text,
    )


@handler("backfill_embeddings")
async def handle_backfill_embeddings(
    organization_id: int,
    batch_size: int = 50,
    source_types: list[str] | None = None,
) -> None:
    """Backfill embeddings for historical memory data."""
    from app.db.session import get_session_factory
    from app.services.embedding import backfill_embeddings

    factory = get_session_factory()
    async with factory() as db:
        result = await backfill_embeddings(
            db, organization_id, batch_size=batch_size, source_types=source_types,
        )
        logger.info("Backfill embeddings result for org %d: %s", organization_id, result)


@handler("batch_score_contacts")
async def handle_batch_score_contacts(
    organization_id: int,
    limit: int = 500,
) -> None:
    """Batch rescore all contacts for an organization."""
    from app.db.session import get_session_factory
    from app.services.contact_intelligence import batch_score_contacts

    factory = get_session_factory()
    async with factory() as db:
        result = await batch_score_contacts(db, organization_id=organization_id, limit=limit)
        logger.info("Batch score contacts result for org %d: %s", organization_id, result)
