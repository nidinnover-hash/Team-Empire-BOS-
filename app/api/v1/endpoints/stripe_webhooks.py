"""Stripe webhook ingestion — real-time charge, refund, and dispute events."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db

router = APIRouter(prefix="/stripe", tags=["Stripe Webhooks"])
logger = logging.getLogger(__name__)

_HANDLED_EVENTS = {
    "charge.succeeded",
    "charge.failed",
    "charge.refunded",
    "charge.dispute.created",
}


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Stripe webhook signature (v1 scheme)."""
    try:
        parts = dict(p.split("=", 1) for p in sig_header.split(","))
        timestamp = parts.get("t", "")
        signature = parts.get("v1", "")
        if not timestamp or not signature:
            return False
        # Reject if timestamp is older than 5 minutes
        if abs(time.time() - int(timestamp)) > 300:
            return False
        signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
        expected = hmac.new(
            secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_signature: str | None = Header(None),
) -> dict:
    """Receive Stripe webhook events and persist transactions."""
    body = await request.body()

    # Verify signature if secret is configured
    if settings.STRIPE_WEBHOOK_SECRET:
        if not stripe_signature:
            raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
        if not _verify_stripe_signature(body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET):
            raise HTTPException(status_code=400, detail="Invalid signature")

    import json
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None

    event_type = event.get("type", "")
    event_id = event.get("id", "")

    if event_type not in _HANDLED_EVENTS:
        return {"status": "ignored", "event_type": event_type}

    obj = event.get("data", {}).get("object", {})
    if not obj:
        return {"status": "ignored", "reason": "no data object"}

    from sqlalchemy import select

    from app.models.contact import Contact
    from app.models.stripe_transaction import StripeTransaction

    # Determine transaction type and extract fields
    if event_type.startswith("charge.dispute"):
        txn_type = "dispute"
        stripe_id = obj.get("id", event_id)
        amount = (obj.get("amount", 0) or 0) / 100.0
        status = obj.get("status", "unknown")
        customer_email = None
    else:
        txn_type = "refund" if "refund" in event_type else "charge"
        stripe_id = obj.get("id", event_id)
        amount = (obj.get("amount", 0) or 0) / 100.0
        status = obj.get("status", "unknown")
        customer_email = (obj.get("billing_details") or {}).get("email") or obj.get("receipt_email")

    currency = obj.get("currency", "usd")
    description = obj.get("description")
    customer_name = (obj.get("billing_details") or {}).get("name")
    stripe_customer_id = obj.get("customer")

    # Check for duplicate
    existing = await db.execute(
        select(StripeTransaction).where(StripeTransaction.stripe_id == stripe_id)
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "stripe_id": stripe_id}

    # Link to contact by email if possible
    contact_id = None
    if customer_email:
        contact_q = await db.execute(
            select(Contact.id).where(Contact.email == customer_email).limit(1)
        )
        row = contact_q.first()
        if row:
            contact_id = row[0]

    # We need an org_id — for webhook events, use the account from Stripe or default org 1
    # In production, you'd map the Stripe account to an org
    org_id = 1

    txn = StripeTransaction(
        organization_id=org_id,
        stripe_id=stripe_id,
        transaction_type=txn_type,
        amount=amount,
        currency=currency,
        status=status,
        customer_email=customer_email,
        customer_name=customer_name,
        stripe_customer_id=stripe_customer_id,
        contact_id=contact_id,
        description=description,
    )
    db.add(txn)
    await db.commit()

    logger.info("Stripe webhook: persisted %s %s ($%.2f)", txn_type, stripe_id, amount)
    return {"status": "processed", "transaction_type": txn_type, "stripe_id": stripe_id}
