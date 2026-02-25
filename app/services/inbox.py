from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.schemas.inbox import UnifiedConversation, UnifiedInboxItem
from app.services import conversation as conversation_service
from app.services import email_service, whatsapp_service


def _sort_key(item: UnifiedInboxItem) -> datetime:
    ts = item.timestamp
    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return ts


def _conversation_key(item: UnifiedInboxItem) -> tuple[str, str]:
    if item.channel == "email":
        if item.from_address:
            return ("email", item.from_address.lower())
        if item.to_address:
            return ("email", item.to_address.lower())
        return ("email", f"item:{item.item_id}")
    if item.channel == "whatsapp":
        if item.from_address:
            return ("whatsapp", item.from_address)
        if item.to_address:
            return ("whatsapp", item.to_address)
        return ("whatsapp", f"item:{item.item_id}")
    return (item.channel, f"item:{item.item_id}")


async def get_unified_inbox(
    db: AsyncSession,
    org_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[UnifiedInboxItem]:
    """
    Return a merged inbox timeline of emails and WhatsApp messages.
    """
    fetch_count = max(limit + offset, limit)
    emails = await email_service.list_emails(
        db,
        org_id=org_id,
        limit=fetch_count,
        offset=0,
        unread_only=False,
    )
    wa_messages = await whatsapp_service.list_whatsapp_messages(
        db,
        org_id=org_id,
        limit=fetch_count,
    )

    items: list[UnifiedInboxItem] = []
    for email in emails:
        preview = (email.ai_summary or email.body_text or "")[:200] if (email.ai_summary or email.body_text) else None
        status = "replied" if email.reply_sent else "pending"
        items.append(
            UnifiedInboxItem(
                channel="email",
                item_id=email.id,
                external_id=email.gmail_id,
                direction="inbound",
                from_address=email.from_address,
                to_address=email.to_address,
                subject=email.subject,
                preview=preview,
                status=status,
                is_read=email.is_read,
                timestamp=email.received_at or email.created_at,
            )
        )

    for msg in wa_messages:
        preview = msg.body_text[:200] if msg.body_text else None
        items.append(
            UnifiedInboxItem(
                channel="whatsapp",
                item_id=msg.id,
                external_id=msg.wa_message_id,
                direction=msg.direction,
                from_address=msg.from_number,
                to_address=msg.to_number,
                subject=None,
                preview=preview,
                status=msg.status,
                is_read=None,
                timestamp=msg.occurred_at or msg.created_at,
            )
        )

    items.sort(key=_sort_key, reverse=True)
    return items[offset: offset + limit]


async def get_conversation_by_id(
    db: AsyncSession,
    org_id: int,
    channel: str,
    participant_key: str,
) -> UnifiedConversation | None:
    """Return a single conversation by channel + participant_key. O(messages) not O(all_conversations)."""
    all_items = await get_unified_inbox(db=db, org_id=org_id, limit=200, offset=0)
    # Match using the same key logic as _conversation_key
    target_key = (channel, participant_key.lower() if channel == "email" else participant_key)
    items = [i for i in all_items if _conversation_key(i) == target_key]
    if not items:
        return None
    items.sort(key=_sort_key, reverse=True)
    last_item = items[0]
    participant = last_item.from_address or last_item.to_address
    record = await conversation_service.create_if_missing(
        db=db,
        org_id=org_id,
        channel=channel,
        participant_key=participant_key,
        participant_display=participant,
        last_message_at=last_item.timestamp,
    )
    unread_count = sum(1 for i in items if i.channel == "email" and i.is_read is False)
    return UnifiedConversation(
        record_id=record.id,
        conversation_id=f"{channel}:{participant_key}",
        channel=channel,
        participant=participant,
        owner_user_id=record.owner_user_id,
        priority=record.priority,
        status=record.status,
        sla_due_at=record.sla_due_at,
        message_count=len(items),
        unread_count=unread_count,
        last_message=cast(UnifiedInboxItem, last_item),
    )


async def get_unified_conversations(
    db: AsyncSession,
    org_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[UnifiedConversation]:
    """
    Return grouped conversation summaries across email and WhatsApp channels.

    Batch-loads existing Conversation records in a single query to avoid
    N+1 DB round trips (one per grouped conversation key).
    """
    all_items = await get_unified_inbox(
        db=db,
        org_id=org_id,
        limit=500,
        offset=0,
    )
    grouped: dict[tuple[str, str], list[UnifiedInboxItem]] = {}
    for item in all_items:
        key = _conversation_key(item)
        grouped.setdefault(key, []).append(item)

    # Batch-load all existing conversation records for this org in 1 query
    existing_result = await db.execute(
        select(Conversation).where(Conversation.organization_id == org_id).limit(5000)
    )
    existing_map: dict[tuple[str, str], Conversation] = {
        (c.channel, c.participant_key): c for c in existing_result.scalars().all()
    }

    # Only call create_if_missing for conversations not already in DB
    conversations: list[UnifiedConversation] = []
    for (channel, participant_key), items in grouped.items():
        items.sort(key=_sort_key, reverse=True)
        last_item = items[0]
        participant = last_item.from_address or last_item.to_address
        record = existing_map.get((channel, participant_key))
        if record is None:
            record = await conversation_service.create_if_missing(
                db=db,
                org_id=org_id,
                channel=channel,
                participant_key=participant_key,
                participant_display=participant,
                last_message_at=last_item.timestamp,
            )
        unread_count = sum(
            1 for i in items if i.channel == "email" and i.is_read is False
        )
        conversations.append(
            UnifiedConversation(
                record_id=record.id,
                conversation_id=f"{channel}:{participant_key}",
                channel=channel,
                participant=participant,
                owner_user_id=record.owner_user_id,
                priority=record.priority,
                status=record.status,
                sla_due_at=record.sla_due_at,
                message_count=len(items),
                unread_count=unread_count,
                last_message=cast(UnifiedInboxItem, last_item),
            )
        )

    conversations.sort(key=lambda c: _sort_key(c.last_message), reverse=True)
    return conversations[offset: offset + limit]
