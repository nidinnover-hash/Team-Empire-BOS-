"""Tests for batch 9 features: attachments (existing), activity timeline, custom fields,
email templates, deal stage requirements, contact segments, outbound webhooks."""

import pytest

# ── Activity timeline ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_timeline(client):
    r = await client.get("/api/v1/activity/timeline?days=7")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert "entity_counts" in body
    assert "total_in_period" in body


@pytest.mark.asyncio
async def test_activity_timeline_filter(client):
    r = await client.get("/api/v1/activity/timeline?entity_type=task&days=3")
    assert r.status_code == 200


# ── Custom fields ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_custom_field(client):
    r = await client.post("/api/v1/custom-fields/definitions", json={
        "entity_type": "contact", "field_key": "industry",
        "field_label": "Industry", "field_type": "text",
    })
    assert r.status_code == 201
    assert r.json()["field_key"] == "industry"


@pytest.mark.asyncio
async def test_list_custom_fields(client):
    await client.post("/api/v1/custom-fields/definitions", json={
        "entity_type": "deal", "field_key": "region",
        "field_label": "Region", "field_type": "select",
    })
    r = await client.get("/api/v1/custom-fields/definitions?entity_type=deal")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_set_and_get_custom_field_value(client):
    # Create definition
    d = await client.post("/api/v1/custom-fields/definitions", json={
        "entity_type": "contact", "field_key": "tier",
        "field_label": "Tier", "field_type": "text",
    })
    defn_id = d.json()["id"]

    # Create contact
    ct = await client.post("/api/v1/contacts", json={"name": "CF Test"})
    contact_id = ct.json()["id"]

    # Set value
    r = await client.post("/api/v1/custom-fields/values", json={
        "field_definition_id": defn_id, "entity_id": contact_id, "value": "Enterprise",
    })
    assert r.status_code == 200
    assert r.json()["value"] == "Enterprise"

    # Get values
    r2 = await client.get(f"/api/v1/custom-fields/values/contact/{contact_id}")
    assert r2.status_code == 200
    vals = r2.json()
    tier_val = [v for v in vals if v["field_key"] == "tier"]
    assert len(tier_val) == 1
    assert tier_val[0]["value"] == "Enterprise"


@pytest.mark.asyncio
async def test_delete_custom_field(client):
    d = await client.post("/api/v1/custom-fields/definitions", json={
        "entity_type": "task", "field_key": "effort_hrs",
        "field_label": "Effort Hours", "field_type": "number",
    })
    defn_id = d.json()["id"]
    r = await client.delete(f"/api/v1/custom-fields/definitions/{defn_id}")
    assert r.status_code == 204


# ── Email templates ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_email_template(client):
    r = await client.post("/api/v1/email-templates", json={
        "name": "Welcome", "subject": "Welcome {{name}}!",
        "body": "Hi {{name}}, welcome to {{company}}.",
        "category": "onboarding",
    })
    assert r.status_code == 201
    assert r.json()["name"] == "Welcome"


@pytest.mark.asyncio
async def test_list_email_templates(client):
    await client.post("/api/v1/email-templates", json={
        "name": "Follow Up", "subject": "Following up",
        "body": "Just checking in.",
    })
    r = await client.get("/api/v1/email-templates")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_render_email_template(client):
    t = await client.post("/api/v1/email-templates", json={
        "name": "Render Test", "subject": "Hello {{name}}",
        "body": "Dear {{name}}, your order #{{order_id}} is confirmed.",
    })
    tid = t.json()["id"]

    r = await client.post(f"/api/v1/email-templates/{tid}/render", json={
        "variables": {"name": "Nidin", "order_id": "12345"},
    })
    assert r.status_code == 200
    assert r.json()["subject"] == "Hello Nidin"
    assert "12345" in r.json()["body"]
    assert "Nidin" in r.json()["body"]


@pytest.mark.asyncio
async def test_update_email_template(client):
    t = await client.post("/api/v1/email-templates", json={
        "name": "To Patch", "subject": "Old", "body": "Old body",
    })
    tid = t.json()["id"]
    r = await client.patch(f"/api/v1/email-templates/{tid}", json={"name": "Patched"})
    assert r.status_code == 200
    assert r.json()["name"] == "Patched"


@pytest.mark.asyncio
async def test_delete_email_template(client):
    t = await client.post("/api/v1/email-templates", json={
        "name": "To Delete", "subject": "X", "body": "X",
    })
    tid = t.json()["id"]
    r = await client.delete(f"/api/v1/email-templates/{tid}")
    assert r.status_code == 204


# ── Deal stage requirements ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_deal_requirement(client):
    r = await client.post("/api/v1/deals/requirements", json={
        "stage": "proposal", "title": "Send pricing doc",
        "is_mandatory": True,
    })
    assert r.status_code == 201
    assert r.json()["title"] == "Send pricing doc"


@pytest.mark.asyncio
async def test_list_deal_requirements(client):
    await client.post("/api/v1/deals/requirements", json={
        "stage": "negotiation", "title": "Legal review",
    })
    r = await client.get("/api/v1/deals/requirements?stage=negotiation")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_check_requirement_and_validate(client):
    # Create requirement
    req = await client.post("/api/v1/deals/requirements", json={
        "stage": "contract", "title": "Sign NDA", "is_mandatory": True,
    })
    req_id = req.json()["id"]

    # Create deal
    deal = await client.post("/api/v1/deals", json={
        "title": "Req Test Deal", "value": 5000, "stage": "discovery",
    })
    deal_id = deal.json()["id"]

    # Validate before checking — should block
    v1 = await client.get(f"/api/v1/deals/requirements/validate/{deal_id}/contract")
    assert v1.status_code == 200
    assert v1.json()["can_enter"] is False
    assert "Sign NDA" in v1.json()["blocking"]

    # Check the requirement
    await client.post(f"/api/v1/deals/requirements/{req_id}/check/{deal_id}", json={})

    # Validate after checking — should pass
    v2 = await client.get(f"/api/v1/deals/requirements/validate/{deal_id}/contract")
    assert v2.json()["can_enter"] is True


@pytest.mark.asyncio
async def test_deal_checklist(client):
    await client.post("/api/v1/deals/requirements", json={
        "stage": "won", "title": "Payment received",
    })
    deal = await client.post("/api/v1/deals", json={
        "title": "Checklist Deal", "value": 1000,
    })
    r = await client.get(f"/api/v1/deals/requirements/checklist/{deal.json()['id']}/won")
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ── Contact segments ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_segment(client):
    r = await client.post("/api/v1/contact-segments", json={
        "name": "VIP Contacts", "filters": {"lead_score_min": 80},
    })
    assert r.status_code == 201
    assert r.json()["name"] == "VIP Contacts"


@pytest.mark.asyncio
async def test_list_segments(client):
    await client.post("/api/v1/contact-segments", json={
        "name": "New Leads", "filters": {"pipeline_stage": "new"},
    })
    r = await client.get("/api/v1/contact-segments")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_evaluate_segment(client):
    # Create contacts
    await client.post("/api/v1/contacts", json={"name": "High Score", "lead_score": 90})
    await client.post("/api/v1/contacts", json={"name": "Low Score", "lead_score": 10})

    # Create segment
    s = await client.post("/api/v1/contact-segments", json={
        "name": "High Scorers", "filters": {"lead_score_min": 50},
    })
    sid = s.json()["id"]

    r = await client.get(f"/api/v1/contact-segments/{sid}/evaluate")
    assert r.status_code == 200
    body = r.json()
    assert body["segment_name"] == "High Scorers"
    assert body["match_count"] >= 1


@pytest.mark.asyncio
async def test_delete_segment(client):
    s = await client.post("/api/v1/contact-segments", json={
        "name": "To Delete", "filters": {},
    })
    sid = s.json()["id"]
    r = await client.delete(f"/api/v1/contact-segments/{sid}")
    assert r.status_code == 204


# ── Outbound webhooks ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_outbound_webhook(client):
    r = await client.post("/api/v1/outbound-webhooks", json={
        "name": "Slack Notify", "url": "https://hooks.slack.com/test",
        "event_types": ["deal_won", "task_completed"],
    })
    assert r.status_code == 201
    assert r.json()["name"] == "Slack Notify"


@pytest.mark.asyncio
async def test_list_outbound_webhooks(client):
    await client.post("/api/v1/outbound-webhooks", json={
        "name": "CRM Sync", "url": "https://crm.example.com/webhook",
    })
    r = await client.get("/api/v1/outbound-webhooks")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_outbound_webhook_test_match(client):
    await client.post("/api/v1/outbound-webhooks", json={
        "name": "All Events", "url": "https://example.com/hook",
        "event_types": ["*"],
    })
    r = await client.get("/api/v1/outbound-webhooks/test-match?event_type=deal_won")
    assert r.status_code == 200
    assert r.json()["event_type"] == "deal_won"
    assert len(r.json()["matching_webhooks"]) >= 1


@pytest.mark.asyncio
async def test_delete_outbound_webhook(client):
    wh = await client.post("/api/v1/outbound-webhooks", json={
        "name": "To Delete", "url": "https://example.com/del",
    })
    wh_id = wh.json()["id"]
    r = await client.delete(f"/api/v1/outbound-webhooks/{wh_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_outbound_webhook_match_logic():
    """Unit test for match_event."""
    from app.services.outbound_webhook import match_event

    class FakeWH:
        event_types_json = '["deal_*", "task_created"]'

    assert match_event("deal_won", FakeWH()) is True
    assert match_event("task_created", FakeWH()) is True
    assert match_event("contact_updated", FakeWH()) is False


@pytest.mark.asyncio
async def test_render_template_logic():
    """Unit test for template rendering."""
    from app.services.email_template import render_template
    result = render_template(
        "Hello {{name}}, your code is {{code}}.",
        "Welcome {{name}}",
        {"name": "Nidin", "code": "ABC123"},
    )
    assert result["subject"] == "Welcome Nidin"
    assert "Nidin" in result["body"]
    assert "ABC123" in result["body"]


# ── Contract test ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_model_contract_batch9():
    """Verify contract test still passes with batch 9 endpoints."""
    from tests.test_api_response_model_contract import test_public_api_routes_have_response_models
    test_public_api_routes_have_response_models()
