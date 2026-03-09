"""Tests for batch 12 features: data retention, score decay, deal velocity,
team quotas, webhook retries, field audit, rate limit config."""

import pytest
from datetime import datetime, UTC, timedelta


# ── Data Retention ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_retention_policy(client):
    r = await client.post("/api/v1/data-retention", json={
        "entity_type": "contact", "action": "archive", "retention_days": 180,
        "condition_field": "status", "condition_value": "inactive",
    })
    assert r.status_code == 201
    assert r.json()["retention_days"] == 180
    assert r.json()["action"] == "archive"


@pytest.mark.asyncio
async def test_list_retention_policies(client):
    await client.post("/api/v1/data-retention", json={
        "entity_type": "event", "action": "purge", "retention_days": 90,
    })
    r = await client.get("/api/v1/data-retention")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_evaluate_retention_policy(client):
    cr = await client.post("/api/v1/data-retention", json={
        "entity_type": "deal", "action": "archive", "retention_days": 365,
    })
    pid = cr.json()["id"]
    r = await client.get(f"/api/v1/data-retention/{pid}/evaluate")
    assert r.status_code == 200
    assert r.json()["dry_run"] is True


@pytest.mark.asyncio
async def test_delete_retention_policy(client):
    cr = await client.post("/api/v1/data-retention", json={
        "entity_type": "task", "action": "purge", "retention_days": 60,
    })
    pid = cr.json()["id"]
    r = await client.delete(f"/api/v1/data-retention/{pid}")
    assert r.status_code == 204


# ── Score Decay ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_decay_rule(client):
    r = await client.post("/api/v1/score-decay", json={
        "name": "Monthly Decay", "inactive_days": 30,
        "decay_points": 10, "min_score": 0, "frequency": "daily",
    })
    assert r.status_code == 201
    assert r.json()["decay_points"] == 10


@pytest.mark.asyncio
async def test_list_decay_rules(client):
    await client.post("/api/v1/score-decay", json={
        "name": "Weekly Decay", "inactive_days": 7, "decay_points": 3,
    })
    r = await client.get("/api/v1/score-decay")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_simulate_decay(client):
    cr = await client.post("/api/v1/score-decay", json={
        "name": "Sim Test", "inactive_days": 14, "decay_points": 5,
    })
    rid = cr.json()["id"]
    r = await client.get(f"/api/v1/score-decay/{rid}/simulate")
    assert r.status_code == 200
    assert r.json()["dry_run"] is True


# ── Deal Velocity ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_deal_transition(client):
    r = await client.post("/api/v1/deal-velocity/transition", json={
        "deal_id": 1, "from_stage": "discovery", "to_stage": "proposal",
        "hours_in_stage": 72.5,
    })
    assert r.status_code == 201
    assert r.json()["to_stage"] == "proposal"
    assert r.json()["hours_in_stage"] == 72.5


@pytest.mark.asyncio
async def test_get_deal_velocity_history(client):
    await client.post("/api/v1/deal-velocity/transition", json={
        "deal_id": 2, "to_stage": "discovery",
    })
    r = await client.get("/api/v1/deal-velocity/history/2")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_stage_velocity(client, monkeypatch):
    from app.services import deal_velocity as dv_svc
    async def fake_velocity(db, organization_id):
        return {"stages": ["discovery", "proposal"], "velocity": {"discovery": {"avg_hours": 48, "transitions": 5}}}
    monkeypatch.setattr(dv_svc, "get_stage_velocity", fake_velocity)
    r = await client.get("/api/v1/deal-velocity/velocity")
    assert r.status_code == 200
    assert "velocity" in r.json()


@pytest.mark.asyncio
async def test_get_bottlenecks(client, monkeypatch):
    from app.services import deal_velocity as dv_svc
    async def fake_bottlenecks(db, organization_id, threshold_hours=48):
        return [{"stage": "negotiation", "avg_hours": 96, "transitions": 10, "exceeds_by_hours": 48}]
    monkeypatch.setattr(dv_svc, "get_bottlenecks", fake_bottlenecks)
    r = await client.get("/api/v1/deal-velocity/bottlenecks")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ── Team Quotas ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_team_quota(client):
    now = datetime.now(UTC)
    r = await client.post("/api/v1/team-quotas", json={
        "user_id": 1, "period": "monthly",
        "period_start": now.isoformat(), "period_end": (now + timedelta(days=30)).isoformat(),
        "quota_type": "revenue", "target_value": 50000,
    })
    assert r.status_code == 201
    assert r.json()["target_value"] == 50000
    assert r.json()["current_value"] == 0


@pytest.mark.asyncio
async def test_list_team_quotas(client):
    r = await client.get("/api/v1/team-quotas")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_update_quota_progress(client):
    now = datetime.now(UTC)
    cr = await client.post("/api/v1/team-quotas", json={
        "user_id": 1, "period": "quarterly",
        "period_start": now.isoformat(), "period_end": (now + timedelta(days=90)).isoformat(),
        "quota_type": "deals", "target_value": 20,
    })
    qid = cr.json()["id"]
    r = await client.patch(f"/api/v1/team-quotas/{qid}/progress", json={"value": 12})
    assert r.status_code == 200
    assert r.json()["current_value"] == 12


@pytest.mark.asyncio
async def test_team_progress(client, monkeypatch):
    from app.services import team_quota as tq_svc
    async def fake_progress(db, organization_id, period=None):
        return [{"id": 1, "user_id": 1, "quota_type": "revenue", "period": "monthly",
                 "target_value": 50000, "current_value": 35000, "progress_pct": 70.0}]
    monkeypatch.setattr(tq_svc, "get_team_progress", fake_progress)
    r = await client.get("/api/v1/team-quotas/progress")
    assert r.status_code == 200
    assert r.json()[0]["progress_pct"] == 70.0


# ── Webhook Retries ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_webhook_retry(client):
    r = await client.post("/api/v1/webhook-retries", json={
        "webhook_id": 1, "event_type": "deal.created",
        "payload": {"deal_id": 42}, "max_attempts": 3,
    })
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    assert r.json()["max_attempts"] == 3


@pytest.mark.asyncio
async def test_list_webhook_retries(client, monkeypatch):
    from app.services import webhook_retry as wr_svc
    async def fake_list(db, organization_id, status=None, webhook_id=None, limit=50):
        return []
    monkeypatch.setattr(wr_svc, "list_retries", fake_list)
    r = await client.get("/api/v1/webhook-retries")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_webhook_retry_stats(client, monkeypatch):
    from app.services import webhook_retry as wr_svc
    async def fake_stats(db, organization_id):
        return {"total": 15, "by_status": {"pending": 5, "success": 8, "exhausted": 2}}
    monkeypatch.setattr(wr_svc, "get_retry_stats", fake_stats)
    r = await client.get("/api/v1/webhook-retries/stats")
    assert r.status_code == 200
    assert r.json()["total"] == 15


# ── Field Audit ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_field_change(client):
    r = await client.post("/api/v1/field-audit", json={
        "entity_type": "contact", "entity_id": 1,
        "field_name": "email", "old_value": "old@test.com",
        "new_value": "new@test.com", "change_source": "api",
    })
    assert r.status_code == 201
    assert r.json()["field_name"] == "email"
    assert r.json()["old_value"] == "old@test.com"


@pytest.mark.asyncio
async def test_record_field_changes_batch(client):
    r = await client.post("/api/v1/field-audit/batch", json={
        "entity_type": "deal", "entity_id": 1,
        "changes": [
            {"field": "stage", "old": "discovery", "new": "proposal"},
            {"field": "value", "old": "10000", "new": "15000"},
        ],
        "change_source": "automation",
    })
    assert r.status_code == 201
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_get_entity_field_history(client):
    await client.post("/api/v1/field-audit", json={
        "entity_type": "contact", "entity_id": 99,
        "field_name": "phone", "old_value": None, "new_value": "555-1234",
    })
    r = await client.get("/api/v1/field-audit/entity/contact/99")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_recent_field_changes(client):
    r = await client.get("/api/v1/field-audit/recent")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Rate Limit Config ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_rate_limit(client):
    r = await client.post("/api/v1/rate-limits", json={
        "name": "Contact API", "endpoint_pattern": "/api/v1/contacts*",
        "requests_per_minute": 30, "requests_per_hour": 500, "burst_limit": 5,
    })
    assert r.status_code == 201
    assert r.json()["requests_per_minute"] == 30


@pytest.mark.asyncio
async def test_list_rate_limits(client):
    await client.post("/api/v1/rate-limits", json={
        "name": "Deal API", "endpoint_pattern": "/api/v1/deals*",
    })
    r = await client.get("/api/v1/rate-limits")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_update_rate_limit(client):
    cr = await client.post("/api/v1/rate-limits", json={
        "name": "Update Test", "endpoint_pattern": "/api/v1/tasks*",
    })
    cid = cr.json()["id"]
    r = await client.patch(f"/api/v1/rate-limits/{cid}", json={"requests_per_minute": 100})
    assert r.status_code == 200
    assert r.json()["requests_per_minute"] == 100


@pytest.mark.asyncio
async def test_rate_limit_usage(client, monkeypatch):
    from app.services import rate_limit_config as rl_svc
    async def fake_usage(db, organization_id):
        return [{"id": 1, "name": "Test", "endpoint_pattern": "/api/*",
                 "requests_per_minute": 60, "total_requests": 1000,
                 "total_throttled": 5, "throttle_rate_pct": 0.5}]
    monkeypatch.setattr(rl_svc, "get_usage_summary", fake_usage)
    r = await client.get("/api/v1/rate-limits/usage")
    assert r.status_code == 200
    assert r.json()[0]["total_requests"] == 1000
