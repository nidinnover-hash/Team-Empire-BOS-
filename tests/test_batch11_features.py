"""Tests for batch 11 features: duplicate detection, recurring invoices, role dashboards,
webhook deliveries, contact lifecycle, saved filters, bulk action logs."""

import pytest


# ── Duplicate Detection ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_contact_duplicates(client, monkeypatch):
    from app.services import duplicate_detection as dup_svc
    async def fake_scan(db, organization_id, threshold=60):
        return [{"entity_a_id": 1, "entity_b_id": 2, "match_score": 85, "match_fields": ["email"]}]
    monkeypatch.setattr(dup_svc, "scan_contact_duplicates", fake_scan)
    r = await client.get("/api/v1/duplicates/scan/contacts?threshold=60")
    assert r.status_code == 200
    assert r.json()["total_matches"] == 1


@pytest.mark.asyncio
async def test_list_duplicate_matches(client, monkeypatch):
    from app.services import duplicate_detection as dup_svc
    async def fake_list(db, organization_id, entity_type=None, status="pending", limit=50):
        return []
    monkeypatch.setattr(dup_svc, "list_duplicate_matches", fake_list)
    r = await client.get("/api/v1/duplicates")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_resolve_duplicate(client, monkeypatch):
    from app.services import duplicate_detection as dup_svc
    from datetime import datetime, UTC

    class FakeMatch:
        id = 1; entity_type = "contact"; entity_a_id = 1; entity_b_id = 2
        match_score = 90; match_fields = '["email"]'; status = "merged"
        resolved_by_user_id = 1; created_at = datetime.now(UTC); resolved_at = datetime.now(UTC)

    async def fake_resolve(db, match_id, organization_id, status, user_id):
        return FakeMatch()
    monkeypatch.setattr(dup_svc, "resolve_duplicate", fake_resolve)
    r = await client.patch("/api/v1/duplicates/1/resolve", json={"status": "merged"})
    assert r.status_code == 200
    assert r.json()["status"] == "merged"


# ── Recurring Invoices ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_recurring_invoice(client):
    r = await client.post("/api/v1/recurring-invoices", json={
        "title": "Monthly Hosting", "amount": 99.99,
        "currency": "USD", "frequency": "monthly",
        "line_items": [{"description": "Cloud Hosting", "amount": 99.99}],
    })
    assert r.status_code == 201
    assert r.json()["title"] == "Monthly Hosting"
    assert r.json()["total_generated"] == 0


@pytest.mark.asyncio
async def test_list_recurring_invoices(client):
    await client.post("/api/v1/recurring-invoices", json={
        "title": "Quarterly Report", "amount": 500, "frequency": "quarterly",
    })
    r = await client.get("/api/v1/recurring-invoices")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_update_recurring_invoice(client):
    cr = await client.post("/api/v1/recurring-invoices", json={
        "title": "Old Title", "amount": 100, "frequency": "monthly",
    })
    inv_id = cr.json()["id"]
    r = await client.patch(f"/api/v1/recurring-invoices/{inv_id}", json={"title": "New Title"})
    assert r.status_code == 200
    assert r.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_mark_invoice_generated(client):
    cr = await client.post("/api/v1/recurring-invoices", json={
        "title": "Generate Test", "amount": 50, "frequency": "weekly",
    })
    inv_id = cr.json()["id"]
    r = await client.post(f"/api/v1/recurring-invoices/{inv_id}/generate")
    assert r.status_code == 200
    assert r.json()["total_generated"] == 1


@pytest.mark.asyncio
async def test_due_invoices(client, monkeypatch):
    from app.services import recurring_invoice as inv_svc
    async def fake_due(db, organization_id):
        return []
    monkeypatch.setattr(inv_svc, "get_due_invoices", fake_due)
    r = await client.get("/api/v1/recurring-invoices/due")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Role Dashboards ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_role_layout_default(client):
    r = await client.get("/api/v1/role-dashboards/CEO")
    assert r.status_code == 200
    assert r.json()["role"] == "CEO"
    assert isinstance(r.json()["layout"], list)


@pytest.mark.asyncio
async def test_save_role_layout(client):
    r = await client.put("/api/v1/role-dashboards", json={
        "role": "MANAGER",
        "layout": [{"widget": "tasks", "x": 0, "y": 0, "w": 12, "h": 4}],
        "theme": "dark",
    })
    assert r.status_code == 200
    assert r.json()["saved"] is True


@pytest.mark.asyncio
async def test_list_all_role_layouts(client):
    r = await client.get("/api/v1/role-dashboards")
    assert r.status_code == 200
    roles = [item["role"] for item in r.json()]
    assert "CEO" in roles
    assert "ADMIN" in roles
    assert "MANAGER" in roles


# ── Webhook Deliveries ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_webhook_deliveries(client, monkeypatch):
    from app.services import webhook_delivery as wd_svc
    async def fake_list(db, organization_id, webhook_id=None, status=None, limit=50):
        return []
    monkeypatch.setattr(wd_svc, "list_deliveries", fake_list)
    r = await client.get("/api/v1/webhook-deliveries")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_webhook_delivery_stats(client, monkeypatch):
    from app.services import webhook_delivery as wd_svc
    async def fake_stats(db, organization_id, webhook_id=None):
        return {"total": 10, "by_status": {"success": 8, "failed": 2}}
    monkeypatch.setattr(wd_svc, "get_delivery_stats", fake_stats)
    r = await client.get("/api/v1/webhook-deliveries/stats")
    assert r.status_code == 200
    assert r.json()["total"] == 10


# ── Contact Lifecycle ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transition_lifecycle_stage(client, monkeypatch):
    from app.services import contact_lifecycle as lc_svc
    from datetime import datetime, UTC

    class FakeEvent:
        id = 1; contact_id = 1; from_stage = None; to_stage = "lead"
        changed_by_user_id = 1; reason = None; created_at = datetime.now(UTC)
        organization_id = 1

    async def fake_transition(db, organization_id, contact_id, to_stage, from_stage=None, changed_by=None, reason=None):
        return FakeEvent()
    monkeypatch.setattr(lc_svc, "transition_stage", fake_transition)
    r = await client.post("/api/v1/contact-lifecycle/transition", json={
        "contact_id": 1, "to_stage": "lead",
    })
    assert r.status_code == 201
    assert r.json()["to_stage"] == "lead"


@pytest.mark.asyncio
async def test_get_contact_lifecycle_history(client, monkeypatch):
    from app.services import contact_lifecycle as lc_svc
    async def fake_history(db, organization_id, contact_id):
        return []
    monkeypatch.setattr(lc_svc, "get_contact_history", fake_history)
    r = await client.get("/api/v1/contact-lifecycle/history/1")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_current_lifecycle_stage(client, monkeypatch):
    from app.services import contact_lifecycle as lc_svc
    async def fake_current(db, organization_id, contact_id):
        return "mql"
    monkeypatch.setattr(lc_svc, "get_current_stage", fake_current)
    r = await client.get("/api/v1/contact-lifecycle/current/1")
    assert r.status_code == 200
    assert r.json()["current_stage"] == "mql"


@pytest.mark.asyncio
async def test_lifecycle_stage_counts(client, monkeypatch):
    from app.services import contact_lifecycle as lc_svc
    async def fake_counts(db, organization_id):
        return {"stages": ["lead", "mql", "sql", "opportunity", "customer", "churned"],
                "counts": {"lead": 10, "mql": 5, "sql": 3, "opportunity": 2, "customer": 8, "churned": 1}}
    monkeypatch.setattr(lc_svc, "get_stage_counts", fake_counts)
    r = await client.get("/api/v1/contact-lifecycle/counts")
    assert r.status_code == 200
    assert "stages" in r.json()
    assert "counts" in r.json()


# ── Saved Filters ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_saved_filter(client):
    r = await client.post("/api/v1/saved-filters", json={
        "name": "Hot Leads", "entity_type": "contact",
        "filters": {"lead_score_min": 80, "pipeline_stage": "lead"},
    })
    assert r.status_code == 201
    assert r.json()["name"] == "Hot Leads"


@pytest.mark.asyncio
async def test_list_saved_filters(client):
    await client.post("/api/v1/saved-filters", json={
        "name": "Active Deals", "entity_type": "deal", "filters": {"status": "active"},
    })
    r = await client.get("/api/v1/saved-filters")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_update_saved_filter(client):
    cr = await client.post("/api/v1/saved-filters", json={
        "name": "Old Filter", "entity_type": "task", "filters": {},
    })
    fid = cr.json()["id"]
    r = await client.patch(f"/api/v1/saved-filters/{fid}", json={"name": "Updated Filter"})
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Filter"


@pytest.mark.asyncio
async def test_delete_saved_filter(client):
    cr = await client.post("/api/v1/saved-filters", json={
        "name": "Delete Me", "entity_type": "contact", "filters": {},
    })
    fid = cr.json()["id"]
    r = await client.delete(f"/api/v1/saved-filters/{fid}")
    assert r.status_code == 204


# ── Bulk Action Logs ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_bulk_action_log(client):
    r = await client.post("/api/v1/bulk-action-logs", json={
        "action_type": "import", "entity_type": "contact",
        "total_records": 100, "success_count": 95, "failure_count": 5,
        "details": {"file": "contacts.csv"},
    })
    assert r.status_code == 201
    assert r.json()["total_records"] == 100
    assert r.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_list_bulk_action_logs(client):
    await client.post("/api/v1/bulk-action-logs", json={
        "action_type": "delete", "entity_type": "deal",
        "total_records": 10, "success_count": 10, "failure_count": 0,
    })
    r = await client.get("/api/v1/bulk-action-logs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_bulk_action_log(client):
    cr = await client.post("/api/v1/bulk-action-logs", json={
        "action_type": "update", "entity_type": "task",
        "total_records": 50, "success_count": 48, "failure_count": 2,
    })
    log_id = cr.json()["id"]
    r = await client.get(f"/api/v1/bulk-action-logs/{log_id}")
    assert r.status_code == 200
    assert r.json()["action_type"] == "update"


@pytest.mark.asyncio
async def test_bulk_action_summary(client, monkeypatch):
    from app.services import bulk_action_log as bal_svc
    async def fake_summary(db, organization_id):
        return {"total_operations": 5, "total_records_processed": 500,
                "total_success": 480, "total_failures": 20,
                "by_action_type": {"import": 3, "delete": 2}}
    monkeypatch.setattr(bal_svc, "get_bulk_action_summary", fake_summary)
    r = await client.get("/api/v1/bulk-action-logs/summary")
    assert r.status_code == 200
    assert r.json()["total_operations"] == 5
