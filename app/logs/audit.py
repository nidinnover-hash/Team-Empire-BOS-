from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.event import EventCreate
from app.services import event as event_service


async def record_action(
    db: AsyncSession,
    event_type: str,
    actor_user_id: int | None,
    organization_id: int = 1,
    entity_type: str | None = None,
    entity_id: int | None = None,
    payload_json: dict | None = None,
):
    await event_service.log_event(
        db,
        EventCreate(
            organization_id=organization_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload_json or {},
        ),
    )
