"""Tests for batch 17: subscriptions, drip campaigns, lead score rules,
onboarding checklists, forecast scenarios, feature requests, audit trail."""
from __future__ import annotations

import pytest

from app.services import (
    subscription as sub_svc,
    drip_campaign as drip_svc,
    lead_score_rule as lsr_svc,
    onboarding_checklist as ob_svc,
    forecast_scenario as fs_svc,
    feature_request as fr_svc,
    audit_entry as ae_svc,
)


def _obj(**kw):
    class _O: pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


TS = "2026-03-10T00:00:00+00:00"


# ── Subscriptions ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_plan(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Pro", billing_cycle="monthly",
                    price=99, currency="USD", features_json="[]", is_active=True,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(sub_svc, "create_plan", fake)
    r = await client.post("/api/v1/subscriptions/plans", json={"name": "Pro", "price": 99})
    assert r.status_code == 201
    assert r.json()["name"] == "Pro"


@pytest.mark.asyncio
async def test_create_subscription(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, plan_id=1, contact_id=None,
                    status="active", start_date="2026-03-10", end_date=None,
                    next_billing_date=None, mrr=99, created_at=TS, updated_at=TS)
    monkeypatch.setattr(sub_svc, "create_subscription", fake)
    r = await client.post("/api/v1/subscriptions", json={"plan_id": 1, "start_date": "2026-03-10", "mrr": 99})
    assert r.status_code == 201
    assert r.json()["mrr"] == 99


@pytest.mark.asyncio
async def test_mrr_summary(client, monkeypatch):
    async def fake(db, org_id):
        return {"total_mrr": 5000, "active_subscriptions": 50}
    monkeypatch.setattr(sub_svc, "get_mrr_summary", fake)
    r = await client.get("/api/v1/subscriptions/mrr-summary")
    assert r.status_code == 200
    assert r.json()["total_mrr"] == 5000


# ── Drip Campaigns ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_drip_campaign(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Welcome", description=None,
                    trigger_event=None, is_active=False, total_enrolled=0,
                    total_completed=0, total_unsubscribed=0,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(drip_svc, "create_campaign", fake)
    r = await client.post("/api/v1/drip-campaigns", json={"name": "Welcome"})
    assert r.status_code == 201
    assert r.json()["name"] == "Welcome"


@pytest.mark.asyncio
async def test_add_drip_step(client, monkeypatch):
    async def fake(db, *, organization_id, campaign_id, **kw):
        return _obj(id=1, organization_id=1, campaign_id=1, step_order=1,
                    delay_days=3, subject="Day 3", body="Hello", created_at=TS)
    monkeypatch.setattr(drip_svc, "add_step", fake)
    r = await client.post("/api/v1/drip-campaigns/1/steps", json={"step_order": 1, "delay_days": 3, "subject": "Day 3"})
    assert r.status_code == 201
    assert r.json()["delay_days"] == 3


@pytest.mark.asyncio
async def test_enroll(client, monkeypatch):
    async def fake(db, *, organization_id, campaign_id, contact_id):
        return _obj(id=1, organization_id=1, campaign_id=1, contact_id=10,
                    current_step=0, status="active", enrolled_at=TS, completed_at=None)
    monkeypatch.setattr(drip_svc, "enroll", fake)
    r = await client.post("/api/v1/drip-campaigns/1/enroll", json={"contact_id": 10})
    assert r.status_code == 201
    assert r.json()["contact_id"] == 10


# ── Lead Score Rules ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_lead_score_rule(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Industry match", rule_type="field",
                    field_name="industry", operator="equals", value="tech",
                    score_delta=20, weight=1.0, is_active=True,
                    conditions_json="{}", created_at=TS, updated_at=TS)
    monkeypatch.setattr(lsr_svc, "create_rule", fake)
    r = await client.post("/api/v1/lead-score-rules", json={"name": "Industry match", "field_name": "industry", "operator": "equals", "value": "tech", "score_delta": 20})
    assert r.status_code == 201
    assert r.json()["score_delta"] == 20


@pytest.mark.asyncio
async def test_evaluate_rules(client, monkeypatch):
    async def fake(db, org_id, contact_data):
        return {"total_score": 20, "matched_rules": [{"rule_id": 1, "name": "Industry match", "delta": 20}]}
    monkeypatch.setattr(lsr_svc, "evaluate_rules", fake)
    r = await client.post("/api/v1/lead-score-rules/evaluate", json={"contact_data": {"industry": "tech"}})
    assert r.status_code == 200
    assert r.json()["total_score"] == 20


# ── Onboarding Checklists ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_template(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="New Customer", description=None,
                    steps_json="[]", is_active=True, created_at=TS, updated_at=TS)
    monkeypatch.setattr(ob_svc, "create_template", fake)
    r = await client.post("/api/v1/onboarding/templates", json={"name": "New Customer"})
    assert r.status_code == 201
    assert r.json()["name"] == "New Customer"


@pytest.mark.asyncio
async def test_assign_checklist(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, template_id=1, contact_id=5,
                    deal_id=None, status="in_progress", progress_json="{}",
                    completed_steps=0, total_steps=3, assigned_user_id=None,
                    created_at=TS, completed_at=None)
    monkeypatch.setattr(ob_svc, "assign_checklist", fake)
    r = await client.post("/api/v1/onboarding/checklists", json={"template_id": 1, "contact_id": 5})
    assert r.status_code == 201
    assert r.json()["total_steps"] == 3


@pytest.mark.asyncio
async def test_complete_step(client, monkeypatch):
    async def fake(db, cid, org_id, step_index):
        return _obj(id=1, organization_id=1, template_id=1, contact_id=5,
                    deal_id=None, status="in_progress", progress_json='{"0": true}',
                    completed_steps=1, total_steps=3, assigned_user_id=None,
                    created_at=TS, completed_at=None)
    monkeypatch.setattr(ob_svc, "complete_step", fake)
    r = await client.post("/api/v1/onboarding/checklists/1/complete-step", json={"step_index": 0})
    assert r.status_code == 200
    assert r.json()["completed_steps"] == 1


# ── Forecast Scenarios ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_scenario(client, monkeypatch):
    async def fake(db, *, organization_id, created_by_user_id, **kw):
        return _obj(id=1, organization_id=1, name="Q1 Best", period="2026-Q1",
                    scenario_type="best", total_pipeline=100000,
                    weighted_value=70000, expected_close=50000,
                    assumptions_json="{}", notes=None, created_by_user_id=1,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(fs_svc, "create_scenario", fake)
    r = await client.post("/api/v1/forecast-scenarios", json={"name": "Q1 Best", "period": "2026-Q1", "scenario_type": "best", "total_pipeline": 100000})
    assert r.status_code == 201
    assert r.json()["scenario_type"] == "best"


@pytest.mark.asyncio
async def test_compare_scenarios(client, monkeypatch):
    async def fake(db, org_id, period):
        return {"best": {"total_pipeline": 100000}, "worst": {"total_pipeline": 50000}}
    monkeypatch.setattr(fs_svc, "compare_scenarios", fake)
    r = await client.get("/api/v1/forecast-scenarios/compare/2026-Q1")
    assert r.status_code == 200
    assert "best" in r.json()


# ── Feature Requests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_feature_request(client, monkeypatch):
    async def fake(db, *, organization_id, submitted_by_user_id, **kw):
        return _obj(id=1, organization_id=1, title="Dark mode", description=None,
                    category=None, status="submitted", priority="medium",
                    votes=0, submitted_by_user_id=1, contact_id=None,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(fr_svc, "create_request", fake)
    r = await client.post("/api/v1/feature-requests", json={"title": "Dark mode"})
    assert r.status_code == 201
    assert r.json()["title"] == "Dark mode"


@pytest.mark.asyncio
async def test_vote(client, monkeypatch):
    async def fake(db, rid, org_id):
        return _obj(id=1, organization_id=1, title="Dark mode", description=None,
                    category=None, status="submitted", priority="medium",
                    votes=5, submitted_by_user_id=1, contact_id=None,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(fr_svc, "vote", fake)
    r = await client.post("/api/v1/feature-requests/1/vote")
    assert r.status_code == 200
    assert r.json()["votes"] == 5


@pytest.mark.asyncio
async def test_feature_request_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"submitted": 10, "planned": 3, "shipped": 2}
    monkeypatch.setattr(fr_svc, "get_stats", fake)
    r = await client.get("/api/v1/feature-requests/stats")
    assert r.status_code == 200
    assert r.json()["submitted"] == 10


# ── Audit Trail ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_audit(client, monkeypatch):
    async def fake(db, *, organization_id, user_id, **kw):
        return _obj(id=1, organization_id=1, entity_type="deal", entity_id=10,
                    action="update", user_id=1, changes_json="{}", snapshot_json="{}",
                    ip_address=None, created_at=TS)
    monkeypatch.setattr(ae_svc, "record_audit", fake)
    r = await client.post("/api/v1/audit-trail", json={"entity_type": "deal", "entity_id": 10, "action": "update"})
    assert r.status_code == 201
    assert r.json()["action"] == "update"


@pytest.mark.asyncio
async def test_list_audit_entries(client, monkeypatch):
    async def fake(db, org_id, **kw): return []
    monkeypatch.setattr(ae_svc, "list_entries", fake)
    r = await client.get("/api/v1/audit-trail")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_audit_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"create": 20, "update": 50, "delete": 5}
    monkeypatch.setattr(ae_svc, "get_stats", fake)
    r = await client.get("/api/v1/audit-trail/stats")
    assert r.status_code == 200
    assert r.json()["update"] == 50
