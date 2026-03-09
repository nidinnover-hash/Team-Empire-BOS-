"""Tests for batch 10 features: SLA policies, enrichment queue, approval workflows,
tag management, import/export presets, internal comments, dashboard widgets."""

import pytest


# ── SLA Policies ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_sla_policy(client):
    r = await client.post("/api/v1/sla-policies", json={
        "name": "Fast Response for Proposals",
        "entity_type": "deal",
        "target_field": "stage",
        "target_value": "proposal",
        "response_hours": 4,
        "resolution_hours": 48,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Fast Response for Proposals"
    assert body["response_hours"] == 4
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_list_sla_policies(client):
    await client.post("/api/v1/sla-policies", json={
        "name": "Task SLA", "entity_type": "task",
        "target_field": "priority", "target_value": "1", "response_hours": 2,
    })
    r = await client.get("/api/v1/sla-policies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_sla_breaches(client):
    # Create policy first
    cr = await client.post("/api/v1/sla-policies", json={
        "name": "Breach Test", "entity_type": "deal",
        "target_field": "stage", "target_value": "discovery", "response_hours": 1,
    })
    pid = cr.json()["id"]
    # Record a breach
    r = await client.post(
        f"/api/v1/sla-policies/breaches?policy_id={pid}&entity_type=deal&entity_id=1&breach_type=response"
    )
    assert r.status_code == 201
    assert r.json()["breach_type"] == "response"
    # List breaches
    r2 = await client.get("/api/v1/sla-policies/breaches")
    assert r2.status_code == 200
    assert len(r2.json()) >= 1


@pytest.mark.asyncio
async def test_sla_check(client):
    r = await client.get(
        "/api/v1/sla-policies/check?entity_type=deal&target_field=stage&target_value=proposal&created_at=2025-01-01T00:00:00Z"
    )
    assert r.status_code == 200
    assert "violations" in r.json()


# ── Enrichment Queue ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_enrichment(client, monkeypatch):
    from app.services import enrichment_queue as eq_svc
    from app.models.enrichment_queue import EnrichmentRequest

    class FakeReq:
        id = 1; contact_id = 1; status = "pending"; source = "domain_lookup"
        result_json = None; error_message = None; created_at = None; completed_at = None
        requested_by_user_id = 1; organization_id = 1

    async def fake_enqueue(db, organization_id, contact_id, source="domain_lookup", requested_by=None):
        return FakeReq()

    monkeypatch.setattr(eq_svc, "enqueue", fake_enqueue)
    r = await client.post("/api/v1/enrichment-queue", json={"contact_id": 1})
    assert r.status_code == 201
    assert r.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_list_enrichment_queue(client, monkeypatch):
    from app.services import enrichment_queue as eq_svc
    async def fake_list(db, organization_id, status=None, limit=50):
        return []
    monkeypatch.setattr(eq_svc, "list_queue", fake_list)
    r = await client.get("/api/v1/enrichment-queue")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_enrichment_stats(client, monkeypatch):
    from app.services import enrichment_queue as eq_svc
    async def fake_stats(db, organization_id):
        return {"total": 5, "by_status": {"pending": 3, "completed": 2}}
    monkeypatch.setattr(eq_svc, "get_enrichment_stats", fake_stats)
    r = await client.get("/api/v1/enrichment-queue/stats")
    assert r.status_code == 200
    assert r.json()["total"] == 5


# ── Approval Workflows ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_approval_workflow(client):
    r = await client.post("/api/v1/approval-workflows", json={
        "name": "High Value Deal",
        "entity_type": "deal",
        "trigger_condition": "value>10000",
    })
    assert r.status_code == 201
    assert r.json()["name"] == "High Value Deal"


@pytest.mark.asyncio
async def test_list_approval_workflows(client):
    await client.post("/api/v1/approval-workflows", json={
        "name": "Expense Approval", "entity_type": "expense", "trigger_condition": "amount>5000",
    })
    r = await client.get("/api/v1/approval-workflows")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_approval_workflow_steps(client):
    cr = await client.post("/api/v1/approval-workflows", json={
        "name": "Step Test", "entity_type": "deal", "trigger_condition": "value>1000",
    })
    wf_id = cr.json()["id"]
    # Add step
    sr = await client.post(f"/api/v1/approval-workflows/{wf_id}/steps", json={
        "step_order": 1, "approver_role": "MANAGER", "escalation_hours": 12,
    })
    assert sr.status_code == 201
    assert sr.json()["approver_role"] == "MANAGER"
    # List steps
    lr = await client.get(f"/api/v1/approval-workflows/{wf_id}/steps")
    assert lr.status_code == 200
    assert len(lr.json()) >= 1


@pytest.mark.asyncio
async def test_approval_workflow_detail(client):
    cr = await client.post("/api/v1/approval-workflows", json={
        "name": "Detail Test", "entity_type": "deal", "trigger_condition": "any",
    })
    wf_id = cr.json()["id"]
    r = await client.get(f"/api/v1/approval-workflows/{wf_id}")
    assert r.status_code == 200
    assert "steps" in r.json()


# ── Tag Management ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_tag(client):
    r = await client.post("/api/v1/tags", json={"name": "VIP", "color": "#ff0000"})
    assert r.status_code == 201
    assert r.json()["name"] == "vip"  # lowercased


@pytest.mark.asyncio
async def test_list_tags(client):
    await client.post("/api/v1/tags", json={"name": "Hot Lead"})
    r = await client.get("/api/v1/tags")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_update_tag(client):
    cr = await client.post("/api/v1/tags", json={"name": "Old Name"})
    tag_id = cr.json()["id"]
    r = await client.patch(f"/api/v1/tags/{tag_id}", json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "new name"


@pytest.mark.asyncio
async def test_merge_tags(client):
    t1 = await client.post("/api/v1/tags", json={"name": "merge-source"})
    t2 = await client.post("/api/v1/tags", json={"name": "merge-target"})
    r = await client.post("/api/v1/tags/merge", json={
        "source_tag_id": t1.json()["id"],
        "target_tag_id": t2.json()["id"],
    })
    assert r.status_code == 200
    assert r.json()["name"] == "merge-target"


@pytest.mark.asyncio
async def test_delete_tag(client):
    cr = await client.post("/api/v1/tags", json={"name": "to-delete"})
    tag_id = cr.json()["id"]
    r = await client.delete(f"/api/v1/tags/{tag_id}")
    assert r.status_code == 204


# ── Import/Export Presets ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_preset(client):
    r = await client.post("/api/v1/import-export-presets", json={
        "name": "Contact CSV Import",
        "direction": "import",
        "entity_type": "contact",
        "column_mapping": {"name": "Full Name", "email": "Email Address"},
    })
    assert r.status_code == 201
    assert r.json()["name"] == "Contact CSV Import"
    assert r.json()["direction"] == "import"


@pytest.mark.asyncio
async def test_list_presets(client):
    await client.post("/api/v1/import-export-presets", json={
        "name": "Deal Export", "direction": "export", "entity_type": "deal",
    })
    r = await client.get("/api/v1/import-export-presets")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_list_presets_filtered(client):
    await client.post("/api/v1/import-export-presets", json={
        "name": "Filter Test", "direction": "import", "entity_type": "contact",
    })
    r = await client.get("/api/v1/import-export-presets?direction=import&entity_type=contact")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_delete_preset(client):
    cr = await client.post("/api/v1/import-export-presets", json={
        "name": "To Delete", "direction": "export", "entity_type": "task",
    })
    pid = cr.json()["id"]
    r = await client.delete(f"/api/v1/import-export-presets/{pid}")
    assert r.status_code == 204


# ── Internal Comments ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_internal_comment(client):
    r = await client.post("/api/v1/internal-comments", json={
        "entity_type": "deal", "entity_id": 1, "body": "This deal looks promising @2",
    })
    assert r.status_code == 200
    assert r.json()["body"] == "This deal looks promising @2"


@pytest.mark.asyncio
async def test_list_internal_comments(client, monkeypatch):
    from app.services import internal_comment as ic_svc
    async def fake_list(db, organization_id, entity_type, entity_id):
        return [{"id": 1, "body": "test", "author_name": "Test", "author_email": "t@t.com",
                 "parent_id": None, "author_user_id": 1, "mentions": [], "created_at": None}]
    monkeypatch.setattr(ic_svc, "list_comments", fake_list)
    r = await client.get("/api/v1/internal-comments?entity_type=deal&entity_id=1")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_delete_internal_comment(client, monkeypatch):
    from app.services import internal_comment as ic_svc
    async def fake_delete(db, comment_id, organization_id, user_id):
        return True
    monkeypatch.setattr(ic_svc, "delete_comment", fake_delete)
    r = await client.delete("/api/v1/internal-comments/1")
    assert r.status_code == 204


# ── Dashboard Widgets ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_dashboard_widget(client):
    r = await client.post("/api/v1/dashboard-widgets", json={
        "name": "My Revenue Chart",
        "widget_type": "chart",
        "data_source": "finance",
        "config": {"chart_type": "line"},
        "default_width": 6,
        "default_height": 4,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "My Revenue Chart"
    assert body["widget_type"] == "chart"


@pytest.mark.asyncio
async def test_list_dashboard_widgets(client):
    await client.post("/api/v1/dashboard-widgets", json={
        "name": "Test Widget", "widget_type": "metric", "data_source": "tasks",
    })
    r = await client.get("/api/v1/dashboard-widgets")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_update_dashboard_widget(client):
    cr = await client.post("/api/v1/dashboard-widgets", json={
        "name": "Old Widget", "widget_type": "table", "data_source": "contacts",
    })
    wid = cr.json()["id"]
    r = await client.patch(f"/api/v1/dashboard-widgets/{wid}", json={"name": "Updated Widget"})
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Widget"


@pytest.mark.asyncio
async def test_delete_dashboard_widget(client):
    cr = await client.post("/api/v1/dashboard-widgets", json={
        "name": "Delete Me", "widget_type": "list", "data_source": "activities",
    })
    wid = cr.json()["id"]
    r = await client.delete(f"/api/v1/dashboard-widgets/{wid}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_system_widget_catalog(client):
    r = await client.get("/api/v1/dashboard-widgets/catalog")
    assert r.status_code == 200
    catalog = r.json()
    assert isinstance(catalog, list)
    assert len(catalog) >= 5
    assert catalog[0]["name"] == "Revenue Overview"
