"""Stripe integration service — connect, sync charges/refunds/disputes with persistence."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import run_with_retry
from app.models.contact import Contact
from app.models.stripe_transaction import StripeTransaction
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
    mark_sync_time,
)
from app.tools import stripe_api

logger = logging.getLogger(__name__)
_TYPE = "stripe"


async def connect_stripe(
    db: AsyncSession, org_id: int, secret_key: str
) -> dict:
    await run_with_retry(lambda: stripe_api.verify_key(secret_key))
    integration = await connect_integration(
        db, organization_id=org_id, integration_type=_TYPE,
        config_json={"api_key": secret_key},
    )
    return {"id": integration.id, "connected": True}


async def get_stripe_status(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False}
    return {
        "connected": True,
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
    }


async def _link_contact_by_email(
    db: AsyncSession, org_id: int, email: str | None,
) -> int | None:
    """Find a contact by email and return its ID."""
    if not email:
        return None
    result = await db.execute(
        select(Contact.id).where(
            Contact.organization_id == org_id,
            Contact.email == email.lower(),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _persist_transactions(
    db: AsyncSession,
    org_id: int,
    charges: list[dict],
    refunds: list[dict],
    disputes: list[dict],
) -> dict:
    """Persist Stripe transactions, dedup by stripe_id, link to contacts."""
    # Load existing stripe_ids for dedup
    existing_q = await db.execute(
        select(StripeTransaction.stripe_id).where(
            StripeTransaction.organization_id == org_id,
        ).limit(10000)
    )
    existing_ids = {row[0] for row in existing_q.all()}

    # Cache email→contact_id lookups
    contact_cache: dict[str, int | None] = {}
    charges_new = refunds_new = disputes_new = 0

    async def _resolve_contact(email: str | None) -> int | None:
        if not email:
            return None
        email_lower = email.lower()
        if email_lower not in contact_cache:
            contact_cache[email_lower] = await _link_contact_by_email(db, org_id, email_lower)
        return contact_cache[email_lower]

    # Persist charges
    for c in charges:
        sid = c.get("id", "")
        if sid in existing_ids:
            continue
        email = (c.get("billing_details") or {}).get("email") or (c.get("receipt_email"))
        cust_name = (c.get("billing_details") or {}).get("name")
        contact_id = await _resolve_contact(email)
        created_ts = c.get("created")
        db.add(StripeTransaction(
            organization_id=org_id,
            stripe_id=sid,
            transaction_type="charge",
            amount=round(c.get("amount", 0) / 100, 2),
            currency=c.get("currency", "usd"),
            status=c.get("status", "unknown"),
            customer_email=email,
            customer_name=cust_name,
            stripe_customer_id=c.get("customer"),
            contact_id=contact_id,
            description=c.get("description"),
            stripe_created_at=datetime.fromtimestamp(created_ts, tz=UTC) if created_ts else None,
        ))
        existing_ids.add(sid)
        charges_new += 1

    # Persist refunds
    for r in refunds:
        sid = r.get("id", "")
        if sid in existing_ids:
            continue
        db.add(StripeTransaction(
            organization_id=org_id,
            stripe_id=sid,
            transaction_type="refund",
            amount=round(r.get("amount", 0) / 100, 2),
            currency=r.get("currency", "usd"),
            status=r.get("status", "unknown"),
            stripe_customer_id=None,
            description=r.get("reason"),
            stripe_created_at=datetime.fromtimestamp(r["created"], tz=UTC) if r.get("created") else None,
        ))
        existing_ids.add(sid)
        refunds_new += 1

    # Persist disputes
    for d in disputes:
        sid = d.get("id", "")
        if sid in existing_ids:
            continue
        db.add(StripeTransaction(
            organization_id=org_id,
            stripe_id=sid,
            transaction_type="dispute",
            amount=round(d.get("amount", 0) / 100, 2),
            currency=d.get("currency", "usd"),
            status=d.get("status", "unknown"),
            description=d.get("reason"),
            stripe_created_at=datetime.fromtimestamp(d["created"], tz=UTC) if d.get("created") else None,
        ))
        existing_ids.add(sid)
        disputes_new += 1

    if charges_new + refunds_new + disputes_new > 0:
        await db.commit()

    return {
        "charges_persisted": charges_new,
        "refunds_persisted": refunds_new,
        "disputes_persisted": disputes_new,
    }


async def sync_stripe_data(
    db: AsyncSession, org_id: int, *, days_back: int = 30
) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("Stripe not connected")
    key = (integration.config_json or {}).get("api_key", "")
    since_ts = int((datetime.now(UTC) - timedelta(days=days_back)).timestamp())
    charges = await run_with_retry(lambda: stripe_api.list_charges(key, limit=100, created_gte=since_ts))
    refunds = await run_with_retry(lambda: stripe_api.list_refunds(key, limit=100, created_gte=since_ts))
    disputes = await run_with_retry(lambda: stripe_api.list_disputes(key, limit=50))

    # Persist transactions to DB
    persist_result = await _persist_transactions(db, org_id, charges, refunds, disputes)

    await mark_sync_time(db, integration)
    return {
        "charges_synced": len(charges),
        "refunds_synced": len(refunds),
        "disputes_synced": len(disputes),
        **persist_result,
        "last_sync_at": datetime.now(UTC).isoformat(),
    }


async def get_financial_summary(
    db: AsyncSession, org_id: int, *, days_back: int = 30
) -> dict:
    """Get a summary of Stripe financial data for layers/memory context."""
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False}
    key = (integration.config_json or {}).get("api_key", "")
    since_ts = int((datetime.now(UTC) - timedelta(days=days_back)).timestamp())
    try:
        balance = await run_with_retry(lambda: stripe_api.get_balance(key))
        charges = await run_with_retry(lambda: stripe_api.list_charges(key, limit=100, created_gte=since_ts))
        refunds = await run_with_retry(lambda: stripe_api.list_refunds(key, limit=50, created_gte=since_ts))
        disputes = await run_with_retry(lambda: stripe_api.list_disputes(key, limit=25))
    except (httpx.HTTPError, RuntimeError, ValueError, TypeError, TimeoutError):
        logger.warning("Failed to fetch Stripe data for org %d", org_id, exc_info=True)
        return {"connected": True, "error": "Failed to fetch Stripe data"}
    total_revenue = sum(c.get("amount", 0) for c in charges if c.get("paid")) / 100
    total_refunded = sum(r.get("amount", 0) for r in refunds) / 100
    return {
        "connected": True,
        "total_charges": len(charges),
        "total_revenue_usd": round(total_revenue, 2),
        "total_refunded_usd": round(total_refunded, 2),
        "disputes_open": len([d for d in disputes if d.get("status") == "needs_response"]),
        "balance": balance,
    }
