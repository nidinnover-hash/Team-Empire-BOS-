"""Tests for batch 3 features: alert scheduler, deal-finance bridge, contact timeline,
Stripe webhooks, export CSV/JSON, deals dashboard."""
from __future__ import annotations

import json
from datetime import date

import pytest


# ── 1. Alert engine in scheduler ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_alert_engine_run_endpoint(client):
    """POST /notifications/run-alerts returns alert summary."""
    resp = await client.post("/api/v1/notifications/run-alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_alerts" in data


# ── 2. Deal-to-finance bridge ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_won_creates_finance_entry(client):
    """Marking a deal as 'won' auto-creates a finance income entry."""
    # Create a deal
    r = await client.post("/api/v1/deals", json={
        "title": "Bridge Deal", "value": 25000.0, "stage": "discovery",
    })
    assert r.status_code == 201
    deal_id = r.json()["id"]

    # Get finance entries before
    before = await client.get("/api/v1/finance")
    before_count = len(before.json()) if before.status_code == 200 else 0

    # Mark deal as won
    resp = await client.patch(f"/api/v1/deals/{deal_id}", json={"stage": "won"})
    assert resp.status_code == 200
    assert resp.json()["stage"] == "won"

    # Check finance entries after — should have one more income entry
    after = await client.get("/api/v1/finance")
    assert after.status_code == 200
    entries = after.json()
    bridge_entries = [e for e in entries if "Bridge Deal" in (e.get("description") or "")]
    assert len(bridge_entries) >= 1
    assert bridge_entries[0]["type"] == "income"
    assert bridge_entries[0]["amount"] == 25000.0


@pytest.mark.asyncio
async def test_deal_won_zero_value_no_finance(client):
    """Deals with value=0 should not create a finance entry."""
    r = await client.post("/api/v1/deals", json={
        "title": "Zero Deal", "value": 0, "stage": "discovery",
    })
    deal_id = r.json()["id"]

    await client.patch(f"/api/v1/deals/{deal_id}", json={"stage": "won"})

    entries = (await client.get("/api/v1/finance")).json()
    zero_entries = [e for e in entries if "Zero Deal" in (e.get("description") or "")]
    assert len(zero_entries) == 0


# ── 3. Contact activity timeline ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_timeline(client):
    """GET /contacts/{id}/timeline returns activity items."""
    # Create a contact
    c = await client.post("/api/v1/contacts", json={
        "name": "Timeline Test", "relationship": "business",
    })
    assert c.status_code == 201
    cid = c.json()["id"]

    # Create a deal linked to this contact
    await client.post("/api/v1/deals", json={
        "title": "Timeline Deal", "contact_id": cid, "value": 5000.0,
    })

    resp = await client.get(f"/api/v1/contacts/{cid}/timeline")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    # Should have at least the deal and the contact_created event
    types = {i["type"] for i in items}
    assert "deal" in types or "event" in types


@pytest.mark.asyncio
async def test_contact_timeline_404(client):
    """Timeline for non-existent contact returns 404."""
    resp = await client.get("/api/v1/contacts/999999/timeline")
    assert resp.status_code == 404


# ── 4. Stripe webhook ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stripe_webhook_charge(client):
    """POST /stripe/webhook processes a charge event."""
    event = {
        "id": "evt_test_1",
        "type": "charge.succeeded",
        "data": {
            "object": {
                "id": "ch_test_001",
                "amount": 5000,
                "currency": "usd",
                "status": "succeeded",
                "description": "Test charge",
                "billing_details": {"email": "buyer@test.com", "name": "Test Buyer"},
                "customer": "cus_test",
            },
        },
    }
    resp = await client.post(
        "/api/v1/stripe/webhook",
        content=json.dumps(event),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["transaction_type"] == "charge"
    assert data["stripe_id"] == "ch_test_001"


@pytest.mark.asyncio
async def test_stripe_webhook_duplicate(client):
    """Duplicate Stripe events are detected."""
    event = {
        "id": "evt_test_dup",
        "type": "charge.succeeded",
        "data": {
            "object": {
                "id": "ch_dup_001",
                "amount": 1000,
                "currency": "usd",
                "status": "succeeded",
            },
        },
    }
    # First call
    r1 = await client.post("/api/v1/stripe/webhook", content=json.dumps(event))
    assert r1.json()["status"] == "processed"

    # Second call — duplicate
    r2 = await client.post("/api/v1/stripe/webhook", content=json.dumps(event))
    assert r2.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_stripe_webhook_ignored_event(client):
    """Unhandled event types are ignored."""
    event = {"id": "evt_test_x", "type": "customer.created", "data": {"object": {}}}
    resp = await client.post("/api/v1/stripe/webhook", content=json.dumps(event))
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── 5. Export endpoints ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_deals_json(client):
    """GET /export/deals returns JSON by default."""
    await client.post("/api/v1/deals", json={"title": "Export Deal", "value": 1000.0})
    resp = await client.get("/api/v1/export/deals")
    assert resp.status_code == 200
    data = resp.json()
    assert "deals" in data
    assert "exported_at" in data


@pytest.mark.asyncio
async def test_export_deals_csv(client):
    """GET /export/deals?fmt=csv returns CSV."""
    await client.post("/api/v1/deals", json={"title": "CSV Deal", "value": 2000.0})
    resp = await client.get("/api/v1/export/deals?fmt=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_export_contacts_json(client):
    """GET /export/contacts returns JSON."""
    resp = await client.get("/api/v1/export/contacts")
    assert resp.status_code == 200
    assert "contacts" in resp.json()


@pytest.mark.asyncio
async def test_export_finance_json(client):
    """GET /export/finance returns JSON."""
    resp = await client.get("/api/v1/export/finance")
    assert resp.status_code == 200
    assert "finance" in resp.json()


# ── 6. Deals dashboard page ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deals_web_page_redirects_unauthenticated(client):
    """GET /web/deals redirects to login without auth."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as anon:
        resp = await anon.get("/web/deals")
        assert resp.status_code == 302
        assert "/web/login" in resp.headers.get("location", "")
