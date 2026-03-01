"""Tests for the 8 new API integrations.

Covers: Perplexity, LinkedIn, Notion, Stripe, Google Analytics,
        Calendly, ElevenLabs, HubSpot.
Each integration tests: connect, status, and primary action endpoint.
All external API calls are monkeypatched to avoid real network calls.
"""
import pytest

from app.services import (
    calendly_service,
    elevenlabs_service,
    google_analytics_service,
    hubspot_service,
    linkedin_service,
    notion_service,
    perplexity_service,
    stripe_service,
)


from tests.conftest import _make_auth_headers


# ── Perplexity ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_perplexity_connect(client, monkeypatch):
    async def fake_connect(db, org_id, api_key):
        return {"id": 99, "connected": True}
    monkeypatch.setattr(perplexity_service, "connect_perplexity", fake_connect)
    resp = await client.post("/api/v1/integrations/perplexity/connect", json={"api_key": "pplx-test"})
    assert resp.status_code == 201
    assert resp.json()["connected"] is True


@pytest.mark.asyncio
async def test_perplexity_status_not_connected(client):
    resp = await client.get("/api/v1/integrations/perplexity/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_perplexity_search_not_connected(client):
    resp = await client.post("/api/v1/integrations/perplexity/search", json={"query": "AI news today"})
    assert resp.status_code == 400


# ── LinkedIn ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_linkedin_connect(client, monkeypatch):
    async def fake_connect(db, org_id, access_token):
        return {"id": 100, "connected": True, "name": "Nidin", "author_urn": "urn:li:person:abc"}
    monkeypatch.setattr(linkedin_service, "connect_linkedin", fake_connect)
    resp = await client.post("/api/v1/integrations/linkedin/connect", json={"access_token": "li-token"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["connected"] is True
    assert data["name"] == "Nidin"


@pytest.mark.asyncio
async def test_linkedin_status_not_connected(client):
    resp = await client.get("/api/v1/integrations/linkedin/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_linkedin_publish_not_connected(client):
    resp = await client.post("/api/v1/integrations/linkedin/publish", json={"text": "Hello LinkedIn!"})
    assert resp.status_code == 400


# ── Notion ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notion_connect(client, monkeypatch):
    async def fake_connect(db, org_id, api_token):
        return {"id": 101, "connected": True, "bot_name": "Clone Bot"}
    monkeypatch.setattr(notion_service, "connect_notion", fake_connect)
    resp = await client.post("/api/v1/integrations/notion/connect", json={"api_token": "ntn-test"})
    assert resp.status_code == 201
    assert resp.json()["connected"] is True


@pytest.mark.asyncio
async def test_notion_status_not_connected(client):
    resp = await client.get("/api/v1/integrations/notion/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_notion_sync_not_connected(client):
    resp = await client.post("/api/v1/integrations/notion/sync")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_notion_sync_malformed_result_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        return {"pages_synced": "2", "notes_created": 1, "last_sync_at": None}

    monkeypatch.setattr(notion_service, "sync_pages_to_notes", fake_sync)
    resp = await client.post("/api/v1/integrations/notion/sync")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_notion_sync_timeout_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        raise TimeoutError("notion timeout")

    monkeypatch.setattr(notion_service, "sync_pages_to_notes", fake_sync)
    resp = await client.post("/api/v1/integrations/notion/sync")
    assert resp.status_code == 502


# ── Stripe ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stripe_connect(client, monkeypatch):
    async def fake_connect(db, org_id, secret_key):
        return {"id": 102, "connected": True}
    monkeypatch.setattr(stripe_service, "connect_stripe", fake_connect)
    resp = await client.post("/api/v1/integrations/stripe/connect", json={"secret_key": "sk_test_123"})
    assert resp.status_code == 201
    assert resp.json()["connected"] is True


@pytest.mark.asyncio
async def test_stripe_status_not_connected(client):
    resp = await client.get("/api/v1/integrations/stripe/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_stripe_sync_not_connected(client):
    resp = await client.post("/api/v1/integrations/stripe/sync")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stripe_sync_malformed_result_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        return {
            "charges_synced": "2",
            "refunds_synced": 1,
            "disputes_synced": 0,
            "last_sync_at": "2026-02-27T00:00:00Z",
        }

    monkeypatch.setattr(stripe_service, "sync_stripe_data", fake_sync)
    resp = await client.post("/api/v1/integrations/stripe/sync")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_stripe_sync_timeout_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        raise TimeoutError("stripe timeout")

    monkeypatch.setattr(stripe_service, "sync_stripe_data", fake_sync)
    resp = await client.post("/api/v1/integrations/stripe/sync")
    assert resp.status_code == 502


# ── Google Analytics ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ga_connect(client, monkeypatch):
    async def fake_connect(db, org_id, access_token, property_id=None):
        return {"id": 106, "connected": True, "property_id": property_id or "123456789"}
    monkeypatch.setattr(google_analytics_service, "connect_google_analytics", fake_connect)
    resp = await client.post(
        "/api/v1/integrations/google-analytics/connect",
        json={"access_token": "ga-token", "property_id": "123456789"},
    )
    assert resp.status_code == 201
    assert resp.json()["connected"] is True
    assert resp.json()["property_id"] == "123456789"


@pytest.mark.asyncio
async def test_ga_status_not_connected(client):
    resp = await client.get("/api/v1/integrations/google-analytics/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_ga_sync_not_connected(client):
    resp = await client.post("/api/v1/integrations/google-analytics/sync")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ga_sync_malformed_result_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        return {
            "sessions_30d": "100",
            "active_users_30d": 50,
            "page_views_30d": 300,
            "top_pages": [],
            "traffic_sources": [],
        }

    monkeypatch.setattr(google_analytics_service, "sync_analytics", fake_sync)
    resp = await client.post("/api/v1/integrations/google-analytics/sync")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_ga_sync_timeout_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        raise TimeoutError("ga timeout")

    monkeypatch.setattr(google_analytics_service, "sync_analytics", fake_sync)
    resp = await client.post("/api/v1/integrations/google-analytics/sync")
    assert resp.status_code == 502


# ── Calendly ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendly_connect(client, monkeypatch):
    async def fake_connect(db, org_id, api_token):
        return {"id": 103, "connected": True, "user_name": "Nidin Nover"}
    monkeypatch.setattr(calendly_service, "connect_calendly", fake_connect)
    resp = await client.post("/api/v1/integrations/calendly/connect", json={"api_token": "cal-test"})
    assert resp.status_code == 201
    assert resp.json()["connected"] is True


@pytest.mark.asyncio
async def test_calendly_status_not_connected(client):
    resp = await client.get("/api/v1/integrations/calendly/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_calendly_sync_not_connected(client):
    resp = await client.post("/api/v1/integrations/calendly/sync")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_calendly_sync_malformed_result_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        return {"events_synced": 2, "upcoming_events": "3", "last_sync_at": None}

    monkeypatch.setattr(calendly_service, "sync_events", fake_sync)
    resp = await client.post("/api/v1/integrations/calendly/sync")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_calendly_sync_timeout_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        raise TimeoutError("calendly timeout")

    monkeypatch.setattr(calendly_service, "sync_events", fake_sync)
    resp = await client.post("/api/v1/integrations/calendly/sync")
    assert resp.status_code == 502


# ── ElevenLabs ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_elevenlabs_connect(client, monkeypatch):
    async def fake_connect(db, org_id, api_key):
        return {"id": 104, "connected": True}
    monkeypatch.setattr(elevenlabs_service, "connect_elevenlabs", fake_connect)
    resp = await client.post("/api/v1/integrations/elevenlabs/connect", json={"api_key": "xi-test"})
    assert resp.status_code == 201
    assert resp.json()["connected"] is True


@pytest.mark.asyncio
async def test_elevenlabs_status_not_connected(client):
    resp = await client.get("/api/v1/integrations/elevenlabs/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_elevenlabs_tts_not_connected(client):
    resp = await client.post("/api/v1/integrations/elevenlabs/tts", json={"text": "Hello world"})
    assert resp.status_code == 400


# ── HubSpot ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hubspot_connect(client, monkeypatch):
    async def fake_connect(db, org_id, access_token):
        return {"id": 105, "connected": True}
    monkeypatch.setattr(hubspot_service, "connect_hubspot", fake_connect)
    resp = await client.post("/api/v1/integrations/hubspot/connect", json={"access_token": "hs-test"})
    assert resp.status_code == 201
    assert resp.json()["connected"] is True


@pytest.mark.asyncio
async def test_hubspot_status_not_connected(client):
    resp = await client.get("/api/v1/integrations/hubspot/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_hubspot_sync_not_connected(client):
    resp = await client.post("/api/v1/integrations/hubspot/sync")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_hubspot_sync_malformed_result_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        return {"contacts_synced": "10", "deals_synced": 2, "last_sync_at": None}

    monkeypatch.setattr(hubspot_service, "sync_hubspot_data", fake_sync)
    resp = await client.post("/api/v1/integrations/hubspot/sync")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_hubspot_sync_timeout_returns_502(client, monkeypatch):
    async def fake_sync(db, org_id):
        raise TimeoutError("hubspot timeout")

    monkeypatch.setattr(hubspot_service, "sync_hubspot_data", fake_sync)
    resp = await client.post("/api/v1/integrations/hubspot/sync")
    assert resp.status_code == 502


# ── Setup Guide includes new integrations ───────────────────────────────

@pytest.mark.asyncio
async def test_setup_guide_includes_new_integrations(client):
    resp = await client.get("/api/v1/integrations/setup-guide")
    assert resp.status_code == 200
    data = resp.json()
    keys = [item["key"] for item in data["items"]]
    for expected in ["perplexity", "linkedin", "notion", "stripe", "google_analytics", "calendly", "elevenlabs", "hubspot"]:
        assert expected in keys, f"{expected} missing from setup guide"
    assert data["total_count"] == 12  # 4 original + 8 new


# ── RBAC: STAFF cannot connect integrations ─────────────────────────────

@pytest.mark.asyncio
async def test_staff_cannot_connect_perplexity(client):
    headers = _make_auth_headers(org_id=1, role="STAFF", user_id=4, email="staff@org1.com")
    resp = await client.post(
        "/api/v1/integrations/perplexity/connect",
        json={"api_key": "test"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_staff_cannot_connect_stripe(client):
    headers = _make_auth_headers(org_id=1, role="STAFF", user_id=4, email="staff@org1.com")
    resp = await client.post(
        "/api/v1/integrations/stripe/connect",
        json={"secret_key": "test"},
        headers=headers,
    )
    assert resp.status_code == 403


# ── Org isolation: org2 CEO cannot see org1 integrations ────────────────

@pytest.mark.asyncio
async def test_org_isolation_perplexity_status(client):
    headers = _make_auth_headers(org_id=2, role="CEO", user_id=2, email="ceo@org2.com")
    resp = await client.get("/api/v1/integrations/perplexity/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_org_isolation_linkedin_status(client):
    headers = _make_auth_headers(org_id=2, role="CEO", user_id=2, email="ceo@org2.com")
    resp = await client.get("/api/v1/integrations/linkedin/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["connected"] is False
