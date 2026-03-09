"""Tests for batch 5 features: email thread summarization, contact network,
notification preferences, deal stage triggers, project timeline page."""

import pytest
from httpx import AsyncClient


# ── Email Thread Summarization ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_thread_summarize_404(client: AsyncClient):
    """POST /email/thread/{thread_id}/summarize returns 404 for empty thread."""
    r = await client.post("/api/v1/email/thread/nonexistent-thread/summarize")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_thread_summarize_with_emails(client: AsyncClient, monkeypatch):
    """Thread summarization returns summary for a thread with emails."""
    from app.services import email_service

    # Mock the AI call
    async def fake_summarize_thread(db, thread_id, org_id, actor_user_id):
        return {
            "thread_id": thread_id,
            "email_count": 3,
            "participants": ["alice@test.com", "bob@test.com"],
            "summary": "Discussion about project timeline and budget.",
        }

    monkeypatch.setattr(email_service, "summarize_thread", fake_summarize_thread)

    r = await client.post("/api/v1/email/thread/test-thread-123/summarize")
    assert r.status_code == 200
    body = r.json()
    assert body["thread_id"] == "test-thread-123"
    assert body["email_count"] == 3
    assert len(body["participants"]) == 2
    assert "summary" in body


# ── Contact Relationship Graph ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_network_404(client: AsyncClient):
    """GET /contacts/{id}/network returns 404 for non-existent contact."""
    r = await client.get("/api/v1/contacts/9999/network")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_contact_network_empty(client: AsyncClient):
    """Contact with no connections returns empty graph."""
    # Create a contact
    cr = await client.post("/api/v1/contacts", json={"name": "Solo Contact"})
    assert cr.status_code == 201
    cid = cr.json()["id"]

    r = await client.get(f"/api/v1/contacts/{cid}/network")
    assert r.status_code == 200
    body = r.json()
    assert body["contact_id"] == cid
    assert body["connection_count"] == 0
    assert body["connections"] == []


@pytest.mark.asyncio
async def test_contact_network_same_company(client: AsyncClient):
    """Contacts with same company appear as connections."""
    c1 = await client.post("/api/v1/contacts", json={"name": "Alice", "company": "Acme Corp"})
    c2 = await client.post("/api/v1/contacts", json={"name": "Bob", "company": "Acme Corp"})
    assert c1.status_code == 201
    assert c2.status_code == 201
    cid1 = c1.json()["id"]

    r = await client.get(f"/api/v1/contacts/{cid1}/network")
    assert r.status_code == 200
    body = r.json()
    assert body["connection_count"] >= 1
    names = [c["name"] for c in body["connections"]]
    assert "Bob" in names


# ── Notification Preferences ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notification_preferences_defaults(client: AsyncClient):
    """GET /notifications/preferences returns all categories with defaults."""
    r = await client.get("/api/v1/notifications/preferences")
    assert r.status_code == 200
    prefs = r.json()
    assert len(prefs) >= 10  # 10 default categories
    cats = [p["event_category"] for p in prefs]
    assert "task" in cats
    assert "deal" in cats
    assert "alert" in cats
    # Default values
    task_pref = next(p for p in prefs if p["event_category"] == "task")
    assert task_pref["in_app"] is True
    assert task_pref["muted"] is False


@pytest.mark.asyncio
async def test_notification_preferences_update(client: AsyncClient):
    """PATCH /notifications/preferences updates a specific category."""
    r = await client.patch("/api/v1/notifications/preferences", json={
        "event_category": "deal",
        "email": True,
        "slack": True,
        "min_severity": "warning",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["event_category"] == "deal"
    assert body["email"] is True
    assert body["slack"] is True
    assert body["min_severity"] == "warning"

    # Verify it persists
    r2 = await client.get("/api/v1/notifications/preferences")
    deal_pref = next(p for p in r2.json() if p["event_category"] == "deal")
    assert deal_pref["email"] is True
    assert deal_pref["slack"] is True


@pytest.mark.asyncio
async def test_notification_preferences_mute(client: AsyncClient):
    """Muting a category sets muted=True."""
    r = await client.patch("/api/v1/notifications/preferences", json={
        "event_category": "system",
        "muted": True,
    })
    assert r.status_code == 200
    assert r.json()["muted"] is True


# ── Deal Stage Automation Triggers ──────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_stage_fires_triggers(client: AsyncClient, monkeypatch):
    """Updating deal stage fires automation triggers."""
    fired = []

    async def fake_fire(db, organization_id, event_type, event_payload=None):
        fired.append({"event_type": event_type, "payload": event_payload})
        return []

    from app.services import automation
    monkeypatch.setattr(automation, "fire_matching_triggers", fake_fire)

    # Create a deal
    cr = await client.post("/api/v1/deals", json={"title": "Trigger Test", "value": 5000, "stage": "discovery"})
    assert cr.status_code == 201
    deal_id = cr.json()["id"]

    # Update stage
    r = await client.patch(f"/api/v1/deals/{deal_id}", json={"stage": "proposal"})
    assert r.status_code == 200

    # Triggers fire from both audit (deal_updated) and stage hook (deal_stage_changed)
    stage_events = [f for f in fired if f["event_type"] == "deal_stage_changed"]
    assert len(stage_events) >= 1
    assert stage_events[0]["payload"]["stage"] == "proposal"


@pytest.mark.asyncio
async def test_deal_stage_trigger_failure_non_fatal(client: AsyncClient, monkeypatch):
    """Trigger failure doesn't break deal update."""
    async def failing_fire(db, organization_id, event_type, event_payload=None):
        raise RuntimeError("trigger engine down")

    from app.services import automation
    monkeypatch.setattr(automation, "fire_matching_triggers", failing_fire)

    cr = await client.post("/api/v1/deals", json={"title": "Fail Test", "value": 1000, "stage": "discovery"})
    assert cr.status_code == 201
    deal_id = cr.json()["id"]

    r = await client.patch(f"/api/v1/deals/{deal_id}", json={"stage": "negotiation"})
    assert r.status_code == 200
    assert r.json()["stage"] == "negotiation"


# ── Project Timeline Page ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_project_timeline_page_redirect(client: AsyncClient):
    """Project timeline page redirects to login without session cookie."""
    from httpx import ASGITransport, AsyncClient as AC
    from app.main import app

    async with AC(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as anon:
        r = await anon.get("/web/project-timeline")
        assert r.status_code in (302, 303, 307)


# ── Notification Preference Service ─────────────────────────────────────

@pytest.mark.asyncio
async def test_should_notify_default(db):
    """should_notify returns default channels when no preference exists."""
    from app.services.notification_preference import should_notify
    result = await should_notify(db, user_id=1, organization_id=1, event_category="task")
    assert result == {"in_app": True, "email": False, "slack": False}


@pytest.mark.asyncio
async def test_should_notify_muted(db):
    """should_notify returns all False when muted."""
    from app.services.notification_preference import upsert_preference, should_notify

    await upsert_preference(db, user_id=1, organization_id=1, event_category="alert", muted=True)
    result = await should_notify(db, user_id=1, organization_id=1, event_category="alert")
    assert result == {"in_app": False, "email": False, "slack": False}


@pytest.mark.asyncio
async def test_should_notify_severity_filter(db):
    """should_notify filters by min_severity."""
    from app.services.notification_preference import upsert_preference, should_notify

    await upsert_preference(db, user_id=1, organization_id=1, event_category="finance", min_severity="warning")
    # "info" is below "warning" threshold
    result = await should_notify(db, user_id=1, organization_id=1, event_category="finance", severity="info")
    assert result == {"in_app": False, "email": False, "slack": False}
    # "critical" is above threshold
    result = await should_notify(db, user_id=1, organization_id=1, event_category="finance", severity="critical")
    assert result["in_app"] is True
