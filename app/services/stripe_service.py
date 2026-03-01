"""Stripe integration service — connect, sync charges/refunds/disputes."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import run_with_retry
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
    await mark_sync_time(db, integration)
    return {
        "charges_synced": len(charges),
        "refunds_synced": len(refunds),
        "disputes_synced": len(disputes),
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
