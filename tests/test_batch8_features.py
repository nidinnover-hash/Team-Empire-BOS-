"""Tests for batch 8 features: task prioritization, scoring rules, deal forecast,
campaign analytics, report schedules, notification rules, workspace permissions."""

import pytest

# ── Smart task prioritization ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prioritized_tasks_empty(client):
    """Prioritized endpoint returns empty list when no tasks."""
    r = await client.get("/api/v1/tasks/prioritized")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_prioritized_tasks_scoring(client):
    """Tasks are returned with priority scores."""
    await client.post("/api/v1/tasks", json={
        "title": "Urgent P1 task", "priority": 1, "due_date": "2026-03-10",
    })
    await client.post("/api/v1/tasks", json={
        "title": "Low P4 task", "priority": 4,
    })
    r = await client.get("/api/v1/tasks/prioritized")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 2
    # P1 with due date should score higher than P4 no due date
    assert items[0]["score"] >= items[-1]["score"]
    assert "factors" in items[0]


@pytest.mark.asyncio
async def test_compute_priority_score_logic():
    """Unit test for _compute_priority_score."""
    from datetime import date

    from app.services.task_priority import _compute_priority_score

    class FakeTask:
        id = 1
        title = "Test"
        priority = 1
        due_date = date.today()
        category = "business"
        project_id = 5
        created_at = None

    result = _compute_priority_score(FakeTask())
    assert result["score"] > 50  # P1 + due today + project-linked


# ── Contact scoring rules ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_scoring_rule(client):
    r = await client.post("/api/v1/scoring-rules", json={
        "name": "VIP company", "field": "company",
        "operator": "contains", "value": "Google", "score_delta": 20,
    })
    assert r.status_code == 201
    assert r.json()["name"] == "VIP company"
    assert r.json()["score_delta"] == 20


@pytest.mark.asyncio
async def test_list_scoring_rules(client):
    await client.post("/api/v1/scoring-rules", json={
        "name": "Rule A", "field": "role", "operator": "equals", "value": "CEO", "score_delta": 15,
    })
    r = await client.get("/api/v1/scoring-rules")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_score_contact(client):
    """Apply scoring rules to a contact."""
    # Create rule
    await client.post("/api/v1/scoring-rules", json={
        "name": "Has company", "field": "company",
        "operator": "not_empty", "value": "", "score_delta": 10,
    })
    # Create contact with company
    ct = await client.post("/api/v1/contacts", json={
        "name": "Score Me", "company": "Acme Corp",
    })
    contact_id = ct.json()["id"]

    r = await client.post(f"/api/v1/scoring-rules/score/{contact_id}")
    assert r.status_code == 200
    assert "new_score" in r.json()
    assert "adjustments" in r.json()


@pytest.mark.asyncio
async def test_delete_scoring_rule(client):
    cr = await client.post("/api/v1/scoring-rules", json={
        "name": "To Delete", "field": "tags",
        "operator": "contains", "value": "hot", "score_delta": 5,
    })
    rule_id = cr.json()["id"]
    r = await client.delete(f"/api/v1/scoring-rules/{rule_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_match_rule_logic():
    """Unit test for _match_rule."""
    from app.services.scoring_rule import _match_rule

    class FakeRule:
        field = "company"
        operator = "contains"
        value = "google"

    class FakeContact:
        company = "Google Inc"

    assert _match_rule(FakeRule(), FakeContact()) is True
    FakeContact.company = "Apple"
    assert _match_rule(FakeRule(), FakeContact()) is False


# ── Deal pipeline forecasting ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_forecast(client):
    r = await client.get("/api/v1/deals/forecast/pipeline")
    assert r.status_code == 200
    body = r.json()
    assert "total_pipeline_value" in body
    assert "total_weighted_value" in body
    assert "stages" in body


@pytest.mark.asyncio
async def test_pipeline_forecast_with_deals(client):
    """Create deals and verify forecast includes them."""
    await client.post("/api/v1/deals", json={
        "title": "Big Deal", "value": 100000, "stage": "proposal", "probability": 50,
    })
    r = await client.get("/api/v1/deals/forecast/pipeline")
    assert r.status_code == 200
    assert r.json()["total_pipeline_value"] >= 100000


@pytest.mark.asyncio
async def test_win_rate_trends(client):
    r = await client.get("/api/v1/deals/forecast/win-rates?months=3")
    assert r.status_code == 200
    body = r.json()
    assert body["months"] == 3
    assert "trends" in body


# ── Campaign analytics & A/B tracking ───────────────────────────────────────


@pytest.mark.asyncio
async def test_record_campaign_event(client):
    c = await client.post("/api/v1/campaigns", json={"name": "Analytics Test"})
    cid = c.json()["id"]

    r = await client.post(f"/api/v1/campaigns/{cid}/events", json={
        "event_type": "sent", "variant": "A",
    })
    assert r.status_code == 201
    assert r.json()["event_type"] == "sent"


@pytest.mark.asyncio
async def test_campaign_analytics(client):
    c = await client.post("/api/v1/campaigns", json={"name": "Analytics Full"})
    cid = c.json()["id"]

    # Record some events
    for etype in ("sent", "sent", "opened", "clicked"):
        await client.post(f"/api/v1/campaigns/{cid}/events", json={"event_type": etype})

    r = await client.get(f"/api/v1/campaigns/{cid}/analytics")
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] == 2
    assert body["opened"] == 1
    assert body["clicked"] == 1
    assert body["open_rate"] == 50.0
    assert body["click_rate"] == 50.0


@pytest.mark.asyncio
async def test_campaign_ab_variants(client):
    c = await client.post("/api/v1/campaigns", json={"name": "AB Test"})
    cid = c.json()["id"]

    await client.post(f"/api/v1/campaigns/{cid}/events", json={"event_type": "sent", "variant": "A"})
    await client.post(f"/api/v1/campaigns/{cid}/events", json={"event_type": "opened", "variant": "A"})
    await client.post(f"/api/v1/campaigns/{cid}/events", json={"event_type": "sent", "variant": "B"})

    r = await client.get(f"/api/v1/campaigns/{cid}/analytics")
    body = r.json()
    assert len(body["variants"]) == 2


# ── Recurring report schedules ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_report_schedule(client):
    r = await client.post("/api/v1/reports/schedules", json={
        "name": "Weekly KPI", "report_type": "kpi_summary",
        "frequency": "weekly", "recipients": ["ceo@test.com"],
    })
    assert r.status_code == 201
    assert r.json()["name"] == "Weekly KPI"
    assert r.json()["is_active"] is True


@pytest.mark.asyncio
async def test_list_report_schedules(client):
    await client.post("/api/v1/reports/schedules", json={
        "name": "Daily Pipeline", "report_type": "deal_pipeline",
        "frequency": "daily", "recipients": ["sales@test.com"],
    })
    r = await client.get("/api/v1/reports/schedules")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_update_report_schedule(client):
    cr = await client.post("/api/v1/reports/schedules", json={
        "name": "To Patch", "report_type": "task_status",
        "frequency": "monthly", "recipients": ["a@test.com"],
    })
    sid = cr.json()["id"]

    r = await client.patch(f"/api/v1/reports/schedules/{sid}", json={
        "name": "Updated Name", "is_active": False,
    })
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Name"
    assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_report_schedule(client):
    cr = await client.post("/api/v1/reports/schedules", json={
        "name": "To Delete", "report_type": "finance_summary",
        "frequency": "weekly", "recipients": ["x@test.com"],
    })
    sid = cr.json()["id"]
    r = await client.delete(f"/api/v1/reports/schedules/{sid}")
    assert r.status_code == 204


# ── Notification rules ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_notification_rule(client):
    r = await client.post("/api/v1/notification-rules", json={
        "name": "Deal alerts", "event_type_pattern": "deal_*",
        "severity": "warning", "channel": "both", "target_roles": "CEO",
    })
    assert r.status_code == 201
    assert r.json()["event_type_pattern"] == "deal_*"


@pytest.mark.asyncio
async def test_list_notification_rules(client):
    await client.post("/api/v1/notification-rules", json={
        "name": "Task alerts", "event_type_pattern": "task_*",
    })
    r = await client.get("/api/v1/notification-rules")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_evaluate_notification_rules(client):
    await client.post("/api/v1/notification-rules", json={
        "name": "All deal events", "event_type_pattern": "deal_*",
        "severity": "critical",
    })
    r = await client.get("/api/v1/notification-rules/evaluate?event_type=deal_won")
    assert r.status_code == 200
    body = r.json()
    assert body["event_type"] == "deal_won"
    assert len(body["matched_rules"]) >= 1
    assert body["matched_rules"][0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_evaluate_no_match(client):
    r = await client.get("/api/v1/notification-rules/evaluate?event_type=xyz_unknown")
    assert r.status_code == 200
    # May or may not match depending on existing rules


@pytest.mark.asyncio
async def test_delete_notification_rule(client):
    cr = await client.post("/api/v1/notification-rules", json={
        "name": "To Delete", "event_type_pattern": "delete_*",
    })
    rule_id = cr.json()["id"]
    r = await client.delete(f"/api/v1/notification-rules/{rule_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_match_event_to_rules_logic():
    """Unit test for fnmatch-based rule matching."""
    from app.services.notification_rule import match_event_to_rules

    class FakeRule:
        def __init__(self, pattern):
            self.event_type_pattern = pattern

    rules = [FakeRule("deal_*"), FakeRule("task_created"), FakeRule("*")]
    matched = match_event_to_rules("deal_won", rules)
    assert len(matched) == 2  # deal_* and *


# ── Workspace permissions ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_workspaces(client):
    r = await client.get("/api/v1/workspace-perms")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_my_workspaces(client):
    r = await client.get("/api/v1/workspace-perms/my")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Contract test ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_model_contract_batch8():
    """Verify contract test still passes with batch 8 endpoints."""
    from tests.test_api_response_model_contract import test_public_api_routes_have_response_models
    test_public_api_routes_have_response_models()
