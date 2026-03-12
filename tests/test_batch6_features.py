"""Tests for batch 6 features: briefing email, merge history, kanban, API usage, team activity."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Briefing email job ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_format_briefing_summary_dict():
    from app.jobs.intelligence import _format_briefing_summary

    result = _format_briefing_summary({
        "total_members": 5,
        "tasks_done": 3,
        "total_tasks_today": 10,
        "pending_approvals": 2,
        "unread_emails": 7,
    })
    assert "5" in result or "total_members" in result.lower()
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_format_briefing_summary_string():
    from app.jobs.intelligence import _format_briefing_summary

    assert _format_briefing_summary("Hello world") == "Hello world"


@pytest.mark.asyncio
async def test_briefing_email_skips_wrong_hour(db):
    """Briefing email job should skip if not 8-9am IST."""
    from app.jobs.intelligence import maybe_send_daily_briefing_email

    with patch("app.jobs.intelligence.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 3, 9, 0, 0, 0, tzinfo=UTC)  # 5:30 IST
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # The function checks local_now.hour, at UTC 0:00 it's 5:30 IST so hour < 8
        await maybe_send_daily_briefing_email(db, org_id=1)
        # Should return early — no error


# ── Contact merge history ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_merge_saves_history(client):
    """Merging contacts should create merge history records."""
    # Create two contacts
    r1 = await client.post("/api/v1/contacts", json={
        "name": "Primary Contact", "email": "primary@test.com",
    })
    assert r1.status_code == 201
    primary_id = r1.json()["id"]

    r2 = await client.post("/api/v1/contacts", json={
        "name": "Dupe Contact", "phone": "+1234567890",
    })
    assert r2.status_code == 201
    dupe_id = r2.json()["id"]

    # Merge
    r3 = await client.post("/api/v1/contacts/merge", json={
        "primary_id": primary_id, "duplicate_ids": [dupe_id],
    })
    assert r3.status_code == 200

    # Check merge history
    r4 = await client.get(f"/api/v1/contacts/{primary_id}/merge-history")
    assert r4.status_code == 200
    history = r4.json()
    assert len(history) == 1
    assert history[0]["merged_contact_id"] == dupe_id
    assert history[0]["undone"] is False
    assert history[0]["merged_contact_snapshot"]["name"] == "Dupe Contact"


@pytest.mark.asyncio
async def test_unmerge_restores_contact(client):
    """Unmerging should re-create the deleted contact."""
    r1 = await client.post("/api/v1/contacts", json={
        "name": "Primary Unmerge", "email": "primary-um@test.com",
    })
    primary_id = r1.json()["id"]

    r2 = await client.post("/api/v1/contacts", json={
        "name": "Dupe Unmerge", "email": "dupe-um@test.com", "phone": "+9999",
    })
    dupe_id = r2.json()["id"]

    await client.post("/api/v1/contacts/merge", json={
        "primary_id": primary_id, "duplicate_ids": [dupe_id],
    })

    # Get history
    r3 = await client.get(f"/api/v1/contacts/{primary_id}/merge-history")
    history_id = r3.json()[0]["id"]

    # Unmerge
    r4 = await client.post(
        f"/api/v1/contacts/{primary_id}/unmerge?merge_history_id={history_id}"
    )
    assert r4.status_code == 200
    restored = r4.json()
    assert restored["name"] == "Dupe Unmerge"
    assert restored["email"] == "dupe-um@test.com"

    # History should now be marked as undone
    r5 = await client.get(f"/api/v1/contacts/{primary_id}/merge-history")
    assert r5.json()[0]["undone"] is True


@pytest.mark.asyncio
async def test_unmerge_not_found(client):
    """Unmerging with invalid history ID should return 404."""
    r = await client.post("/api/v1/contacts/999/unmerge?merge_history_id=99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_merge_history_empty(client):
    """Merge history for contact with no merges should be empty."""
    r1 = await client.post("/api/v1/contacts", json={"name": "Solo Contact"})
    contact_id = r1.json()["id"]
    r2 = await client.get(f"/api/v1/contacts/{contact_id}/merge-history")
    assert r2.status_code == 200
    assert r2.json() == []


# ── Deal pipeline Kanban page ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deal_pipeline_page_redirect(client):
    """Unauthenticated access to deal pipeline should redirect."""
    transport = ASGITransport(app=client._transport.app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        r = await anon.get("/web/deal-pipeline", follow_redirects=False)
        assert r.status_code == 302
        assert "/web/login" in r.headers.get("location", "")


# ── API usage analytics ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_usage_analytics(client):
    """API usage endpoint should return aggregated event data."""
    r = await client.get("/api/v1/ops/api-usage?days=7")
    assert r.status_code == 200
    body = r.json()
    assert "total_events" in body
    assert "by_event_type" in body
    assert "by_day" in body
    assert "by_actor" in body
    assert isinstance(body["by_event_type"], list)


@pytest.mark.asyncio
async def test_api_usage_analytics_default_days(client):
    """API usage endpoint default days param should work."""
    r = await client.get("/api/v1/ops/api-usage")
    assert r.status_code == 200
    assert r.json()["days"] == 7


# ── Team activity feed ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_team_activity_feed(client):
    """Team activity feed should return grouped events."""
    r = await client.get("/api/v1/ops/team-activity?days=3")
    assert r.status_code == 200
    body = r.json()
    assert "total_events" in body
    assert "actors" in body
    assert isinstance(body["actors"], list)


@pytest.mark.asyncio
async def test_team_activity_feed_default(client):
    """Team activity feed defaults should work."""
    r = await client.get("/api/v1/ops/team-activity")
    assert r.status_code == 200
    assert r.json()["days"] == 3


# ── Contact merge history snapshot helper ─────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_contact():
    """_snapshot_contact should capture expected fields."""
    from app.services.contact import _snapshot_contact

    class FakeContact:
        id = 1
        name = "Test"
        email = "test@t.com"
        phone = None
        company = "Acme"
        role = "CEO"
        relationship = "business"
        notes = "Some notes"
        pipeline_stage = "new"
        lead_score = 50
        lead_source = "website"
        deal_value = 5000.0
        tags = "vip,hot"
        source_channel = "web"
        campaign_name = None
        partner_id = None

    snap = _snapshot_contact(FakeContact())
    assert snap["name"] == "Test"
    assert snap["lead_score"] == 50
    assert snap["deal_value"] == 5000.0
    assert snap["company"] == "Acme"


# ── Contract test ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_model_contract():
    """Verify contract test still passes with new endpoints."""
    from tests.test_api_response_model_contract import test_public_api_routes_have_response_models
    test_public_api_routes_have_response_models()
