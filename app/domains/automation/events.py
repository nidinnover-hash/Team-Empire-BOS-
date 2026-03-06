from __future__ import annotations

from app.platform.signals import SignalCategory, SignalEnvelope, publish_signal


async def emit_workflow_signal(
    *,
    topic: str,
    organization_id: int,
    workspace_id: int | None,
    actor_user_id: int | None,
    entity_type: str,
    entity_id: str,
    payload: dict[str, object],
    source: str,
    db,
) -> None:
    category = SignalCategory.DOMAIN
    if topic.startswith("workflow.run") or topic.startswith("workflow.step"):
        category = SignalCategory.EXECUTION
    await publish_signal(
        SignalEnvelope(
            topic=topic,
            category=category,
            organization_id=organization_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        ),
        db=db,
    )
