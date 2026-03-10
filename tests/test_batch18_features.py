"""Tests for batch 18: customer health, meetings, document signing,
leaderboard, dedup rules, stage gates, activity goals."""
from __future__ import annotations

import pytest

from app.services import (
    customer_health as ch_svc,
    meeting_scheduler as ms_svc,
    document_signing as ds_svc,
    sales_leaderboard as lb_svc,
    dedup_rule as dd_svc,
    stage_gate as sg_svc,
    activity_goal as ag_svc,
)


def _obj(**kw):
    class _O: pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


TS = "2026-03-10T00:00:00+00:00"


# ── Customer Health ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_health_score(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, contact_id=5, overall_score=75,
                    usage_score=80, engagement_score=70, support_score=80,
                    payment_score=70, risk_level="monitor", factors_json="{}",
                    previous_score=0, created_at=TS, updated_at=TS)
    monkeypatch.setattr(ch_svc, "upsert_score", fake)
    r = await client.post("/api/v1/customer-health", json={"contact_id": 5, "usage_score": 80, "engagement_score": 70, "support_score": 80, "payment_score": 70})
    assert r.status_code == 201
    assert r.json()["risk_level"] == "monitor"


@pytest.mark.asyncio
async def test_health_summary(client, monkeypatch):
    async def fake(db, org_id):
        return {"healthy": 30, "monitor": 10, "at_risk": 5, "critical": 2}
    monkeypatch.setattr(ch_svc, "get_summary", fake)
    r = await client.get("/api/v1/customer-health/summary")
    assert r.status_code == 200
    assert r.json()["healthy"] == 30


# ── Meetings ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_availability(client, monkeypatch):
    async def fake(db, *, organization_id, user_id, **kw):
        return _obj(id=1, organization_id=1, user_id=1, day_of_week=1,
                    start_time="09:00", end_time="17:00", is_active=True, created_at=TS)
    monkeypatch.setattr(ms_svc, "set_availability", fake)
    r = await client.post("/api/v1/meetings/availability", json={"day_of_week": 1, "start_time": "09:00", "end_time": "17:00"})
    assert r.status_code == 201
    assert r.json()["start_time"] == "09:00"


@pytest.mark.asyncio
async def test_create_booking(client, monkeypatch):
    async def fake(db, *, organization_id, host_user_id, **kw):
        return _obj(id=1, organization_id=1, host_user_id=1, contact_id=None,
                    title="Demo Call", start_at=TS, end_at=TS,
                    status="confirmed", location=None, notes=None,
                    reminder_sent=False, created_at=TS)
    monkeypatch.setattr(ms_svc, "create_booking", fake)
    r = await client.post("/api/v1/meetings/bookings", json={"title": "Demo Call", "start_at": "2026-03-10T10:00:00Z", "end_at": "2026-03-10T11:00:00Z"})
    assert r.status_code == 201
    assert r.json()["title"] == "Demo Call"


# ── Document Signing ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_signature_request(client, monkeypatch):
    async def fake(db, *, organization_id, sent_by_user_id, **kw):
        return _obj(id=1, organization_id=1, title="NDA", document_url=None,
                    deal_id=None, contact_id=None, status="pending",
                    signing_order=1, signers_json="[]", expires_at=None,
                    signed_at=None, sent_by_user_id=1, created_at=TS, updated_at=TS)
    monkeypatch.setattr(ds_svc, "create_request", fake)
    r = await client.post("/api/v1/document-signing", json={"title": "NDA"})
    assert r.status_code == 201
    assert r.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_mark_signed(client, monkeypatch):
    async def fake(db, rid, org_id):
        return _obj(id=1, organization_id=1, title="NDA", document_url=None,
                    deal_id=None, contact_id=None, status="signed",
                    signing_order=1, expires_at=None, signed_at=TS,
                    sent_by_user_id=1, created_at=TS, updated_at=TS)
    monkeypatch.setattr(ds_svc, "mark_signed", fake)
    r = await client.post("/api/v1/document-signing/1/sign")
    assert r.status_code == 200
    assert r.json()["status"] == "signed"


@pytest.mark.asyncio
async def test_signing_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"pending": 5, "signed": 20, "declined": 2}
    monkeypatch.setattr(ds_svc, "get_stats", fake)
    r = await client.get("/api/v1/document-signing/stats")
    assert r.status_code == 200
    assert r.json()["signed"] == 20


# ── Leaderboard ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_leaderboard(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, user_id=1, period="2026-03",
                    period_type="monthly", total_revenue=50000,
                    deals_closed=5, deals_created=10, activities_count=100,
                    rank=1, created_at=TS, updated_at=TS)
    monkeypatch.setattr(lb_svc, "upsert_entry", fake)
    r = await client.post("/api/v1/leaderboard", json={"user_id": 1, "period": "2026-03", "total_revenue": 50000, "deals_closed": 5})
    assert r.status_code == 201
    assert r.json()["total_revenue"] == 50000


@pytest.mark.asyncio
async def test_get_leaderboard(client, monkeypatch):
    async def fake(db, org_id, **kw): return []
    monkeypatch.setattr(lb_svc, "get_leaderboard", fake)
    r = await client.get("/api/v1/leaderboard?period=2026-03")
    assert r.status_code == 200


# ── Dedup Rules ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_dedup_rule(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Email match",
                    match_fields='["email"]', merge_strategy="keep_newest",
                    confidence_threshold=0.8, auto_merge=False, is_active=True,
                    total_matches=0, total_merges=0, created_at=TS, updated_at=TS)
    monkeypatch.setattr(dd_svc, "create_rule", fake)
    r = await client.post("/api/v1/dedup-rules", json={"name": "Email match", "match_fields": ["email"]})
    assert r.status_code == 201
    assert r.json()["name"] == "Email match"


@pytest.mark.asyncio
async def test_check_duplicates(client, monkeypatch):
    async def fake(db, org_id, contact_data):
        return {"potential_duplicates": []}
    monkeypatch.setattr(dd_svc, "check_duplicates", fake)
    r = await client.post("/api/v1/dedup-rules/check", json={"contact_data": {"email": "test@example.com"}})
    assert r.status_code == 200
    assert r.json()["potential_duplicates"] == []


# ── Stage Gates ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_stage_gate(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, stage="negotiation",
                    requirement_type="field", field_name="budget",
                    description="Budget must be set", is_blocking=True,
                    is_active=True, created_at=TS, updated_at=TS)
    monkeypatch.setattr(sg_svc, "create_gate", fake)
    r = await client.post("/api/v1/stage-gates", json={"stage": "negotiation", "field_name": "budget", "description": "Budget must be set"})
    assert r.status_code == 201
    assert r.json()["stage"] == "negotiation"


@pytest.mark.asyncio
async def test_validate_stage(client, monkeypatch):
    async def fake(db, org_id, stage, deal_data):
        return {"stage": "negotiation", "passed": [], "failed": [], "can_proceed": True}
    monkeypatch.setattr(sg_svc, "validate_stage", fake)
    r = await client.post("/api/v1/stage-gates/validate", json={"stage": "negotiation", "deal_data": {"budget": 50000}})
    assert r.status_code == 200
    assert r.json()["can_proceed"] is True


@pytest.mark.asyncio
async def test_record_override(client, monkeypatch):
    async def fake(db, *, organization_id, overridden_by_user_id, **kw):
        return _obj(id=1, organization_id=1, gate_id=1, deal_id=10,
                    overridden_by_user_id=1, reason="CEO approved", created_at=TS)
    monkeypatch.setattr(sg_svc, "record_override", fake)
    r = await client.post("/api/v1/stage-gates/overrides", json={"gate_id": 1, "deal_id": 10, "reason": "CEO approved"})
    assert r.status_code == 201
    assert r.json()["reason"] == "CEO approved"


# ── Activity Goals ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_activity_goal(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, user_id=1, activity_type="calls",
                    period="2026-W10", period_type="weekly", target=20,
                    current=0, streak=0, best_streak=0,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(ag_svc, "create_goal", fake)
    r = await client.post("/api/v1/activity-goals", json={"user_id": 1, "activity_type": "calls", "period": "2026-W10", "target": 20})
    assert r.status_code == 201
    assert r.json()["target"] == 20


@pytest.mark.asyncio
async def test_record_activity(client, monkeypatch):
    async def fake(db, gid, org_id, count=1):
        return _obj(id=1, organization_id=1, user_id=1, activity_type="calls",
                    period="2026-W10", period_type="weekly", target=20,
                    current=5, streak=0, best_streak=0,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(ag_svc, "record_activity", fake)
    r = await client.post("/api/v1/activity-goals/1/record", json={"count": 5})
    assert r.status_code == 200
    assert r.json()["current"] == 5


@pytest.mark.asyncio
async def test_get_progress(client, monkeypatch):
    async def fake(db, org_id, user_id):
        return [{"id": 1, "activity_type": "calls", "target": 20, "current": 15, "pct": 75.0}]
    monkeypatch.setattr(ag_svc, "get_progress", fake)
    r = await client.get("/api/v1/activity-goals/progress/1")
    assert r.status_code == 200
    assert r.json()[0]["pct"] == 75.0
