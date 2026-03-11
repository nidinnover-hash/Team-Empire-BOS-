"""Helpers for critical mutations: always record audit (and optionally approval)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.audit import record_action


async def record_critical_mutation(
    db: AsyncSession,
    *,
    event_type: str,
    organization_id: int,
    actor_user_id: int,
    entity_type: str | None = None,
    entity_id: int | None = None,
    payload_json: dict | None = None,
) -> None:
    """
    Record audit for a critical mutation. Use after any write that must be traced.
    For string ids (e.g. placement_id), pass them in payload_json.
    """
    await record_action(
        db=db,
        event_type=event_type,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=payload_json,
    )
