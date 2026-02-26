from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


def _now() -> datetime:
    return datetime.now(UTC)


async def get_by_key(
    db: AsyncSession,
    org_id: int,
    channel: str,
    participant_key: str,
) -> Conversation | None:
    row = await db.execute(
        select(Conversation).where(
            Conversation.organization_id == org_id,
            Conversation.channel == channel,
            Conversation.participant_key == participant_key,
        )
    )
    return cast(Conversation | None, row.scalar_one_or_none())


async def create_if_missing(
    db: AsyncSession,
    org_id: int,
    channel: str,
    participant_key: str,
    participant_display: str | None,
    last_message_at: datetime | None,
) -> Conversation:
    existing = await get_by_key(db, org_id, channel, participant_key)
    if existing is not None:
        changed = False
        if participant_display and not existing.participant_display:
            existing.participant_display = participant_display
            changed = True
        if last_message_at and (existing.last_message_at is None or last_message_at > existing.last_message_at):
            existing.last_message_at = last_message_at
            changed = True
        if changed:
            existing.updated_at = _now()
            await db.commit()
            await db.refresh(existing)
        return existing

    convo = Conversation(
        organization_id=org_id,
        channel=channel,
        participant_key=participant_key,
        participant_display=participant_display,
        last_message_at=last_message_at,
        priority="medium",
        status="new",
        updated_at=_now(),
    )
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo


async def update_assignment(
    db: AsyncSession,
    org_id: int,
    channel: str,
    participant_key: str,
    owner_user_id: int | None,
) -> Conversation | None:
    convo = await get_by_key(db, org_id, channel, participant_key)
    if convo is None:
        return None
    convo.owner_user_id = owner_user_id
    convo.updated_at = _now()
    await db.commit()
    await db.refresh(convo)
    return convo


async def update_state(
    db: AsyncSession,
    org_id: int,
    channel: str,
    participant_key: str,
    status: str | None = None,
    priority: str | None = None,
    sla_due_at: datetime | None = None,
    update_sla_due_at: bool = False,
) -> Conversation | None:
    convo = await get_by_key(db, org_id, channel, participant_key)
    if convo is None:
        return None
    if status is not None:
        convo.status = status
    if priority is not None:
        convo.priority = priority
    if update_sla_due_at:
        convo.sla_due_at = sla_due_at
    convo.updated_at = _now()
    await db.commit()
    await db.refresh(convo)
    return convo
