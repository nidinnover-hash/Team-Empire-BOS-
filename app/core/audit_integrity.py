"""Immutable audit ledger — HMAC chain signing and tamper detection.

Each audit event is signed with HMAC-SHA256. The signature includes the
previous event's hash, creating a verifiable chain of trust.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _derive_audit_key() -> bytes:
    """Derive a dedicated HMAC key from SECRET_KEY for audit signing."""
    from app.core.config import settings
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        b"audit-ledger-integrity",
        hashlib.sha256,
    ).digest()


def compute_event_signature(
    event_id: int,
    org_id: int,
    event_type: str,
    created_at: datetime,
    payload_json: dict[str, Any] | None,
    prev_hash: str | None,
) -> str:
    """Compute HMAC-SHA256 signature for an audit event."""
    payload_str = json.dumps(payload_json or {}, sort_keys=True, default=str)
    created_str = created_at.isoformat() if created_at else ""
    message = f"{event_id}|{org_id}|{event_type}|{created_str}|{payload_str}|{prev_hash or 'GENESIS'}"
    return hmac.new(
        _derive_audit_key(),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def get_last_event_hash(
    db: AsyncSession,
    organization_id: int,
    *,
    exclude_id: int | None = None,
) -> str | None:
    """Fetch the signature of the most recent event for an org."""
    from app.models.event import Event

    query = (
        select(Event.signature)
        .where(Event.organization_id == organization_id)
        .order_by(Event.id.desc())
        .limit(1)
    )
    if exclude_id is not None:
        query = query.where(Event.id != exclude_id)
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    return row


async def sign_event(db: AsyncSession, event: Any) -> None:
    """Compute and set signature + prev_hash on an event, then flush."""
    from app.core.config import settings
    if not settings.AUDIT_INTEGRITY_ENABLED:
        return

    prev_hash = await get_last_event_hash(db, event.organization_id, exclude_id=event.id)
    event.prev_hash = prev_hash

    event.signature = compute_event_signature(
        event_id=event.id,
        org_id=event.organization_id,
        event_type=event.event_type,
        created_at=event.created_at,
        payload_json=event.payload_json,
        prev_hash=prev_hash,
    )
    await db.flush()


async def verify_chain(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 1000,
) -> dict[str, Any]:
    """Walk the audit chain and verify each event's signature and linkage.

    Returns ``{"valid": True/False, "checked": N, "first_broken_id": ...}``.
    """
    from app.models.event import Event

    result = await db.execute(
        select(Event)
        .where(Event.organization_id == organization_id)
        .order_by(Event.id.asc())
        .limit(limit)
    )
    events = list(result.scalars().all())

    if not events:
        return {"valid": True, "checked": 0, "first_broken_id": None}

    prev_sig: str | None = None
    for idx, evt in enumerate(events):
        # Skip unsigned legacy events
        if evt.signature is None:
            prev_sig = None
            continue

        # Verify chain linkage
        if evt.prev_hash != prev_sig:
            return {"valid": False, "checked": idx + 1, "first_broken_id": evt.id}

        # Verify signature
        expected = compute_event_signature(
            event_id=evt.id,
            org_id=evt.organization_id,
            event_type=evt.event_type,
            created_at=evt.created_at,
            payload_json=evt.payload_json,
            prev_hash=evt.prev_hash,
        )
        if not hmac.compare_digest(evt.signature, expected):
            return {"valid": False, "checked": idx + 1, "first_broken_id": evt.id}

        prev_sig = evt.signature

    return {"valid": True, "checked": len(events), "first_broken_id": None}
