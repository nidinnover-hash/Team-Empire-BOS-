from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whatsapp_message import WhatsAppMessage
from app.services import integration as integration_service


def _parse_ts(ts: str | int | None) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


async def _find_existing_message(
    db: AsyncSession,
    org_id: int,
    wa_message_id: str,
) -> WhatsAppMessage | None:
    row = await db.execute(
        select(WhatsAppMessage).where(
            WhatsAppMessage.organization_id == org_id,
            WhatsAppMessage.wa_message_id == wa_message_id,
        )
    )
    return cast(WhatsAppMessage | None, row.scalar_one_or_none())


async def ingest_webhook_payload(db: AsyncSession, payload: dict) -> int:
    """
    Persist inbound WhatsApp webhook messages/statuses.
    Returns number of rows inserted or updated.
    """
    changes_count = 0
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            phone_number_id = metadata.get("phone_number_id")
            if not isinstance(phone_number_id, str) or not phone_number_id:
                continue

            integration = await integration_service.find_whatsapp_integration_by_phone_number_id(
                db, phone_number_id=phone_number_id
            )
            if integration is None:
                continue
            org_id = integration.organization_id

            messages = value.get("messages")
            if isinstance(messages, list):
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    wa_message_id = msg.get("id")
                    if not isinstance(wa_message_id, str) or not wa_message_id:
                        continue
                    existing = await _find_existing_message(db, org_id, wa_message_id)
                    if existing is not None:
                        continue

                    text = msg.get("text") or {}
                    body = text.get("body") if isinstance(text, dict) else None
                    row = WhatsAppMessage(
                        organization_id=org_id,
                        integration_id=integration.id,
                        wa_message_id=wa_message_id,
                        wa_contact_id=msg.get("from"),
                        direction="inbound",
                        from_number=msg.get("from"),
                        to_number=metadata.get("display_phone_number"),
                        message_type=msg.get("type"),
                        body_text=body if isinstance(body, str) else None,
                        status="received",
                        occurred_at=_parse_ts(msg.get("timestamp")),
                        raw_payload=msg,
                    )
                    db.add(row)
                    changes_count += 1

            statuses = value.get("statuses")
            if isinstance(statuses, list):
                for status in statuses:
                    if not isinstance(status, dict):
                        continue
                    wa_message_id = status.get("id")
                    if not isinstance(wa_message_id, str) or not wa_message_id:
                        continue
                    existing = await _find_existing_message(db, org_id, wa_message_id)
                    status_text = status.get("status")
                    status_str = status_text if isinstance(status_text, str) else None
                    if existing is None:
                        row = WhatsAppMessage(
                            organization_id=org_id,
                            integration_id=integration.id,
                            wa_message_id=wa_message_id,
                            wa_contact_id=status.get("recipient_id"),
                            direction="outbound",
                            from_number=metadata.get("display_phone_number"),
                            to_number=status.get("recipient_id"),
                            message_type="text",
                            body_text=None,
                            status=status_str,
                            occurred_at=_parse_ts(status.get("timestamp")),
                            raw_payload=status,
                        )
                        db.add(row)
                    else:
                        existing.status = status_str
                        if existing.occurred_at is None:
                            existing.occurred_at = _parse_ts(status.get("timestamp"))
                        existing.raw_payload = status
                    changes_count += 1

    if changes_count:
        await db.commit()
    return changes_count


async def list_whatsapp_messages(
    db: AsyncSession,
    org_id: int,
    limit: int = 100,
) -> list[WhatsAppMessage]:
    row = await db.execute(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.organization_id == org_id)
        .order_by(WhatsAppMessage.occurred_at.desc(), WhatsAppMessage.created_at.desc())
        .limit(limit)
    )
    return list(row.scalars().all())
