"""Tests for innovation endpoints — sales coaching, experiments, cross-layer, CTO, system health, clone memory."""
import pytest

# ── Sales Interactions ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_sales_interaction(client):
    resp = await client.post(
        "/api/v1/sales/interactions?employee_id=1&interaction_type=call&outcome=lost"
        "&objection_encountered=too+expensive&response_given=explained+value&loss_reason=budget"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_list_sales_interactions(client):
    resp = await client.get("/api/v1/sales/interactions")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_sales_loss_patterns_empty(client):
    resp = await client.get("/api/v1/sales/loss-patterns")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_lost"] == 0


@pytest.mark.asyncio
async def test_sales_win_patterns_empty(client):
    resp = await client.get("/api/v1/sales/win-patterns")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_won"] == 0


@pytest.mark.asyncio
async def test_sales_playbook_empty(client):
    resp = await client.get("/api/v1/sales/playbook")
    assert resp.status_code == 200
    data = resp.json()
    assert "playbook" in data
    assert "conversion_rate" in data


@pytest.mark.asyncio
async def test_sales_employee_stats(client):
    resp = await client.get("/api/v1/sales/employee-stats/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["employee_id"] == 1
    assert "conversion_rate" in data


# ── Cross-Layer Intelligence ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_layer_analysis(client):
    resp = await client.get("/api/v1/intelligence/cross-layer?window_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "composite_health" in data
    assert "insights" in data
    assert "layer_scores" in data


# ── Layer Score Trends ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_layers(client):
    resp = await client.post("/api/v1/layers/snapshot?window_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "written" in data


@pytest.mark.asyncio
async def test_layer_trend_empty(client):
    resp = await client.get("/api/v1/layers/trend/marketing?limit=12")
    assert resp.status_code == 200
    data = resp.json()
    assert data["layer"] == "marketing"
    assert "points" in data


@pytest.mark.asyncio
async def test_all_layer_trends(client):
    resp = await client.get("/api/v1/layers/trends?limit=4")
    assert resp.status_code == 200
    data = resp.json()
    assert "marketing" in data


# ── Policy Effectiveness ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_effectiveness_empty(client):
    resp = await client.get("/api/v1/governance/policy-effectiveness?weeks=4")
    assert resp.status_code == 200
    data = resp.json()
    assert "policies_analyzed" in data
    assert "recommendations" in data


# ── CTO Strategic Review ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cto_strategic_review(client, monkeypatch):
    async def fake_ai(*args, **kwargs):
        return "**7-Day Priorities**: 1. Fix revenue pipeline."

    monkeypatch.setattr("app.services.cto_strategic.call_ai", fake_ai, raising=False)
    resp = await client.post("/api/v1/brain/cto-strategic-review?challenge=grow+revenue")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "strategic_plan" in data
    assert "next_actions" in data


# ── System Health ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_system_health_summary(client):
    resp = await client.get("/api/v1/system/health?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "health_score" in data
    assert "total_events" in data


@pytest.mark.asyncio
async def test_system_health_events(client):
    resp = await client.get("/api/v1/system/health/events")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data


@pytest.mark.asyncio
async def test_system_health_autopsy(client):
    resp = await client.get("/api/v1/system/health/autopsy?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "recommendations" in data
    assert "health_score" in data


# ── Innovation Experiments ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_experiment(client):
    resp = await client.post(
        "/api/v1/experiments?title=Test+Experiment"
        "&hypothesis=Doubling+outreach+will+increase+leads"
        "&success_metric=leads_per_week&area=marketing"
        "&baseline_value=10&target_value=20"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "proposed"


@pytest.mark.asyncio
async def test_list_experiments(client):
    resp = await client.get("/api/v1/experiments")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_experiment_lifecycle(client):
    # Create
    resp = await client.post(
        "/api/v1/experiments?title=Lifecycle+Test"
        "&hypothesis=Testing+flow&success_metric=completion"
    )
    assert resp.status_code == 200
    exp_id = resp.json()["id"]

    # Start
    resp = await client.post(f"/api/v1/experiments/{exp_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # Complete
    resp = await client.post(
        f"/api/v1/experiments/{exp_id}/complete"
        "?actual_value=15&outcome=success&outcome_notes=Exceeded+target"
    )
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "success"


@pytest.mark.asyncio
async def test_innovation_velocity(client):
    resp = await client.get("/api/v1/experiments/velocity?days=90")
    assert resp.status_code == 200
    data = resp.json()
    assert "experiments_per_month" in data
    assert "success_rate" in data


# ── Clone Memory ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_clone_memory(client):
    resp = await client.post(
        "/api/v1/clone/memory?employee_id=1"
        "&situation=Client+asked+about+pricing"
        "&action_taken=Offered+volume+discount"
        "&outcome=success&category=sales&tags=pricing,discount"
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_search_clone_memory(client):
    # Store first
    await client.post(
        "/api/v1/clone/memory?employee_id=1"
        "&situation=Budget+objection+from+enterprise+client"
        "&action_taken=Showed+ROI+calculator"
        "&outcome=success&category=sales&tags=objection,budget"
    )
    # Search
    resp = await client.get(
        "/api/v1/clone/memory/search?employee_id=1&query=budget"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1


@pytest.mark.asyncio
async def test_reinforce_clone_memory(client):
    resp = await client.post(
        "/api/v1/clone/memory?employee_id=1"
        "&situation=test+reinforce&action_taken=tested&outcome=success"
    )
    memory_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/clone/memory/{memory_id}/reinforce?boost=0.1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_clone_memory_stats(client):
    resp = await client.get("/api/v1/clone/memory/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_memories" in data
    assert "by_category" in data
