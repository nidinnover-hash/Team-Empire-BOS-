from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.inbox import UnifiedInboxItem
from app.services import email_service, whatsapp_service


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

    items.sort(key=lambda x: x.timestamp or 0, reverse=True)
    return items[offset: offset + limit]
