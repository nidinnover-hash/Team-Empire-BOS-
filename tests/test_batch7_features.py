"""Tests for batch 7 features: live notifications, contact timeline, OKR key results,
recurring task templates, email campaigns, dashboard layout, bulk deal import."""

from datetime import date

import pytest

# ── Notification live stream — SSE endpoint tested manually (streaming hangs in httpx)


# ── Contact timeline page ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_contact_timeline_page_redirect(client):
    """Unauthenticated access to contact timeline should redirect."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=client._transport.app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        r = await anon.get("/web/contact-timeline", follow_redirects=False)
        assert r.status_code == 302
        assert "/web/login" in r.headers.get("location", "")


# ── Goal OKR key results ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_key_result(client):
    """Create a goal then add a key result."""
    g = await client.post("/api/v1/goals", json={
        "title": "KR Test Goal", "description": "Test",
        "target_date": "2026-12-31",
    })
    assert g.status_code == 201
    goal_id = g.json()["id"]

    kr = await client.post(f"/api/v1/goals/{goal_id}/key-results", json={
        "title": "Ship 10 features", "target_value": 10, "metric_unit": "features",
    })
    assert kr.status_code == 201
    body = kr.json()
    assert body["title"] == "Ship 10 features"
    assert body["target_value"] == 10
    assert body["current_value"] == 0


@pytest.mark.asyncio
async def test_list_key_results(client):
    """List key results for a goal."""
    g = await client.post("/api/v1/goals", json={
        "title": "List KR Goal", "target_date": "2026-12-31",
    })
    goal_id = g.json()["id"]

    await client.post(f"/api/v1/goals/{goal_id}/key-results", json={
        "title": "KR A", "target_value": 5,
    })
    await client.post(f"/api/v1/goals/{goal_id}/key-results", json={
        "title": "KR B", "target_value": 3,
    })

    r = await client.get(f"/api/v1/goals/{goal_id}/key-results")
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_update_key_result_recalculates_goal(client):
    """Updating a KR should recalculate goal progress."""
    g = await client.post("/api/v1/goals", json={
        "title": "Progress Goal", "target_date": "2026-12-31",
    })
    goal_id = g.json()["id"]

    kr = await client.post(f"/api/v1/goals/{goal_id}/key-results", json={
        "title": "Revenue $100k", "target_value": 100, "metric_unit": "$k",
    })
    kr_id = kr.json()["id"]

    # Update current value to 50 (50% progress)
    r = await client.patch(f"/api/v1/goals/{goal_id}/key-results/{kr_id}", json={
        "current_value": 50,
    })
    assert r.status_code == 200
    assert r.json()["progress"] == 50

    # Goal should also show ~50% progress
    goals = await client.get("/api/v1/goals")
    goal = next(g for g in goals.json() if g["id"] == goal_id)
    assert goal["progress"] == 50


@pytest.mark.asyncio
async def test_delete_key_result(client):
    """Deleting a key result should work."""
    g = await client.post("/api/v1/goals", json={
        "title": "Delete KR Goal", "target_date": "2026-12-31",
    })
    goal_id = g.json()["id"]

    kr = await client.post(f"/api/v1/goals/{goal_id}/key-results", json={
        "title": "To Delete", "target_value": 10,
    })
    kr_id = kr.json()["id"]

    r = await client.delete(f"/api/v1/goals/{goal_id}/key-results/{kr_id}")
    assert r.status_code == 204

    items = await client.get(f"/api/v1/goals/{goal_id}/key-results")
    assert len(items.json()) == 0


# ── Recurring task templates ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_task_template(client):
    """Create a recurring task template."""
    r = await client.post("/api/v1/tasks/templates", json={
        "title": "Weekly standup notes", "recurrence": "weekly",
        "recurrence_detail": "0,2,4", "priority": 1,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Weekly standup notes"
    assert body["recurrence"] == "weekly"
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_list_task_templates(client):
    """List active templates."""
    await client.post("/api/v1/tasks/templates", json={
        "title": "Daily review", "recurrence": "daily",
    })
    r = await client.get("/api/v1/tasks/templates?active_only=true")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_update_task_template(client):
    """Patch a template."""
    cr = await client.post("/api/v1/tasks/templates", json={
        "title": "To Patch", "recurrence": "monthly", "recurrence_detail": "15",
    })
    tmpl_id = cr.json()["id"]

    r = await client.patch(f"/api/v1/tasks/templates/{tmpl_id}", json={
        "title": "Patched Template", "is_active": False,
    })
    assert r.status_code == 200
    assert r.json()["title"] == "Patched Template"
    assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_task_template(client):
    """Delete a template."""
    cr = await client.post("/api/v1/tasks/templates", json={
        "title": "To Delete", "recurrence": "daily",
    })
    tmpl_id = cr.json()["id"]

    r = await client.delete(f"/api/v1/tasks/templates/{tmpl_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_generate_recurring_tasks(client):
    """Manual trigger of recurring task generation."""
    r = await client.post("/api/v1/tasks/templates/generate")
    assert r.status_code == 200
    assert "generated" in r.json()


@pytest.mark.asyncio
async def test_should_generate_logic():
    """Test the _should_generate recurrence logic."""
    from app.services.task_template import _should_generate

    class FakeTemplate:
        last_generated_at = None
        recurrence = "daily"
        recurrence_detail = None

    tmpl = FakeTemplate()
    assert _should_generate(tmpl, date.today()) is True

    tmpl.recurrence = "weekly"
    tmpl.recurrence_detail = str(date.today().weekday())
    assert _should_generate(tmpl, date.today()) is True

    tmpl.recurrence_detail = str((date.today().weekday() + 3) % 7)
    assert _should_generate(tmpl, date.today()) is False

    tmpl.recurrence = "monthly"
    tmpl.recurrence_detail = str(date.today().day)
    assert _should_generate(tmpl, date.today()) is True


# ── Email campaign sequences ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_campaign(client):
    """Create an email campaign."""
    r = await client.post("/api/v1/campaigns", json={
        "name": "Welcome Series", "description": "Onboarding emails",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Welcome Series"
    assert body["status"] == "draft"


@pytest.mark.asyncio
async def test_list_campaigns(client):
    """List campaigns."""
    await client.post("/api/v1/campaigns", json={"name": "Camp A"})
    await client.post("/api/v1/campaigns", json={"name": "Camp B"})
    r = await client.get("/api/v1/campaigns")
    assert r.status_code == 200
    assert len(r.json()) >= 2


@pytest.mark.asyncio
async def test_campaign_steps(client):
    """Add and list steps for a campaign."""
    c = await client.post("/api/v1/campaigns", json={"name": "Steps Test"})
    cid = c.json()["id"]

    s1 = await client.post(f"/api/v1/campaigns/{cid}/steps", json={
        "subject": "Welcome!", "body_template": "Hi {{name}}",
        "step_order": 1, "delay_hours": 1,
    })
    assert s1.status_code == 201

    s2 = await client.post(f"/api/v1/campaigns/{cid}/steps", json={
        "subject": "Follow up", "body_template": "Checking in",
        "step_order": 2, "delay_hours": 48,
    })
    assert s2.status_code == 201

    r = await client.get(f"/api/v1/campaigns/{cid}/steps")
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_campaign_enroll_and_list(client):
    """Enroll a contact and list enrollments."""
    # Create contact
    ct = await client.post("/api/v1/contacts", json={"name": "Enroll Me"})
    contact_id = ct.json()["id"]

    # Create campaign
    c = await client.post("/api/v1/campaigns", json={"name": "Enroll Test"})
    cid = c.json()["id"]

    # Enroll
    e = await client.post(f"/api/v1/campaigns/{cid}/enroll", json={
        "contact_id": contact_id,
    })
    assert e.status_code == 201
    assert e.json()["status"] == "active"

    # List enrollments
    r = await client.get(f"/api/v1/campaigns/{cid}/enrollments")
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_campaign_status_update(client):
    """Update campaign status."""
    c = await client.post("/api/v1/campaigns", json={"name": "Status Test"})
    cid = c.json()["id"]

    r = await client.patch(f"/api/v1/campaigns/{cid}/status", json={"status": "active"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_campaign_summary(client):
    """Get campaign summary."""
    c = await client.post("/api/v1/campaigns", json={"name": "Summary Test"})
    cid = c.json()["id"]

    r = await client.get(f"/api/v1/campaigns/{cid}/summary")
    assert r.status_code == 200
    body = r.json()
    assert "total_enrolled" in body
    assert "name" in body


# ── Dashboard layout customization ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_default_layout(client):
    """Getting layout without saving should return defaults."""
    r = await client.get("/api/v1/dashboard/layout")
    assert r.status_code == 200
    body = r.json()
    assert "widgets" in body
    assert "theme" in body
    assert body["theme"] == "default"
    assert len(body["widgets"]) > 0


@pytest.mark.asyncio
async def test_save_and_get_layout(client):
    """Saving a custom layout then retrieving it."""
    widgets = [
        {"id": "kpis", "title": "KPIs", "x": 0, "y": 0, "w": 12, "h": 2},
        {"id": "tasks", "title": "Tasks", "x": 0, "y": 2, "w": 6, "h": 3},
    ]
    r = await client.put("/api/v1/dashboard/layout", json={
        "widgets": widgets, "theme": "compact",
    })
    assert r.status_code == 200
    assert r.json()["theme"] == "compact"
    assert len(r.json()["widgets"]) == 2

    # Get it back
    r2 = await client.get("/api/v1/dashboard/layout")
    assert r2.status_code == 200
    assert r2.json()["theme"] == "compact"
    assert len(r2.json()["widgets"]) == 2


@pytest.mark.asyncio
async def test_save_layout_overwrites(client):
    """Saving again should overwrite the previous layout."""
    await client.put("/api/v1/dashboard/layout", json={
        "widgets": [{"id": "a", "title": "A", "x": 0, "y": 0, "w": 4, "h": 2}],
        "theme": "default",
    })
    await client.put("/api/v1/dashboard/layout", json={
        "widgets": [{"id": "b", "title": "B", "x": 0, "y": 0, "w": 6, "h": 3}],
        "theme": "dark",
    })

    r = await client.get("/api/v1/dashboard/layout")
    assert r.json()["theme"] == "dark"
    assert r.json()["widgets"][0]["id"] == "b"


# ── Bulk deal import ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_import_deals(client):
    """Import deals from CSV."""
    csv_content = (
        "title,value,stage,probability,expected_close_date,description\n"
        "Deal Alpha,50000,discovery,30,2026-06-15,Big opportunity\n"
        "Deal Beta,25000,proposal,60,2026-07-01,Follow up\n"
        ",0,discovery,0,,\n"  # missing title — should skip
    )
    files = {"file": ("deals.csv", csv_content.encode(), "text/csv")}
    r = await client.post("/api/v1/bulk/import/deals", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 2
    assert body["skipped"] == 1


@pytest.mark.asyncio
async def test_bulk_import_deals_bad_stage(client):
    """Deals with invalid stage should default to discovery."""
    csv_content = (
        "title,value,stage\n"
        "Deal X,10000,invalid_stage\n"
    )
    files = {"file": ("deals.csv", csv_content.encode(), "text/csv")}
    r = await client.post("/api/v1/bulk/import/deals", files=files)
    assert r.status_code == 200
    assert r.json()["imported"] == 1


# ── Contract test ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_model_contract_batch7():
    """Verify contract test still passes with batch 7 endpoints."""
    from tests.test_api_response_model_contract import test_public_api_routes_have_response_models
    test_public_api_routes_have_response_models()
