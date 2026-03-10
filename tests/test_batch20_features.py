"""Tests for batch 20: revenue goals, deal dependencies, contact timeline,
email warmup, territory assignments, quote approvals, win/loss analysis."""
from __future__ import annotations

import pytest

from app.services import (
    revenue_goal as rg_svc,
    deal_dependency as dd_svc,
    contact_timeline_events as ct_svc,
    email_warmup as ew_svc,
    territory_assignment as ta_svc,
    quote_approval as qa_svc,
    win_loss_analysis as wl_svc,
)


def _obj(**kw):
    class _O: pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


TS = "2026-03-10T00:00:00+00:00"


# ── Revenue Goals ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_revenue_goal(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, scope="team", scope_id=5,
                    period="2026-Q1", period_type="quarterly",
                    target_amount=500000, current_amount=0, stretch_amount=600000,
                    attainment_pct=0, gap=500000, status="active",
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(rg_svc, "create_goal", fake)
    r = await client.post("/api/v1/revenue-goals", json={"period": "2026-Q1", "target_amount": 500000, "scope": "team", "scope_id": 5})
    assert r.status_code == 201
    assert r.json()["target_amount"] == 500000


@pytest.mark.asyncio
async def test_gap_analysis(client, monkeypatch):
    async def fake(db, org_id, period):
        return {"period": "2026-Q1", "goal_count": 3, "achieved": 1,
                "total_target": 1500000, "total_current": 800000,
                "total_gap": 700000, "overall_attainment": 53.3}
    monkeypatch.setattr(rg_svc, "get_gap_analysis", fake)
    r = await client.get("/api/v1/revenue-goals/gap-analysis/2026-Q1")
    assert r.status_code == 200
    assert r.json()["total_gap"] == 700000


# ── Deal Dependencies ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_dependency(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, deal_id=10, depends_on_deal_id=20,
                    dependency_type="blocks", is_resolved=False,
                    notes=None, created_at=TS, resolved_at=None)
    monkeypatch.setattr(dd_svc, "create_dependency", fake)
    r = await client.post("/api/v1/deal-dependencies", json={"deal_id": 10, "depends_on_deal_id": 20})
    assert r.status_code == 201
    assert r.json()["is_resolved"] is False


@pytest.mark.asyncio
async def test_resolve_dependency(client, monkeypatch):
    async def fake(db, dep_id, org_id):
        return _obj(id=1, organization_id=1, deal_id=10, depends_on_deal_id=20,
                    dependency_type="blocks", is_resolved=True,
                    notes=None, created_at=TS, resolved_at=TS)
    monkeypatch.setattr(dd_svc, "resolve_dependency", fake)
    r = await client.put("/api/v1/deal-dependencies/1/resolve")
    assert r.status_code == 200
    assert r.json()["is_resolved"] is True


# ── Contact Timeline ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_timeline_event(client, monkeypatch):
    async def fake(db, *, organization_id, actor_user_id, **kw):
        return _obj(id=1, organization_id=1, contact_id=5, event_type="email",
                    event_source="gmail", title="Sent follow-up",
                    description=None, entity_type=None, entity_id=None,
                    actor_user_id=1, occurred_at=TS, created_at=TS)
    monkeypatch.setattr(ct_svc, "add_event", fake)
    r = await client.post("/api/v1/contact-timeline/events", json={
        "contact_id": 5, "event_type": "email", "event_source": "gmail", "title": "Sent follow-up"
    })
    assert r.status_code == 201
    assert r.json()["event_type"] == "email"


@pytest.mark.asyncio
async def test_timeline_summary(client, monkeypatch):
    async def fake(db, org_id, contact_id):
        return {"contact_id": 5, "total_events": 20, "breakdown": {"email": 10, "call": 5, "meeting": 5}}
    monkeypatch.setattr(ct_svc, "get_activity_summary", fake)
    r = await client.get("/api/v1/contact-timeline/summary/5")
    assert r.status_code == 200
    assert r.json()["total_events"] == 20


# ── Email Warmup ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_warmup(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, email_address="sales@example.com",
                    domain="example.com", daily_limit=5, current_daily=0,
                    target_daily=50, ramp_increment=2, warmup_day=1,
                    reputation_score=50, is_active=True,
                    started_at=TS, created_at=TS, updated_at=TS)
    monkeypatch.setattr(ew_svc, "create_warmup", fake)
    r = await client.post("/api/v1/email-warmup", json={"email_address": "sales@example.com", "domain": "example.com"})
    assert r.status_code == 201
    assert r.json()["warmup_day"] == 1


@pytest.mark.asyncio
async def test_warmup_status(client, monkeypatch):
    async def fake(db, org_id):
        return {"total": 3, "active": 2, "completed": 1, "avg_reputation": 72.5}
    monkeypatch.setattr(ew_svc, "get_status", fake)
    r = await client.get("/api/v1/email-warmup/status")
    assert r.status_code == 200
    assert r.json()["avg_reputation"] == 72.5


# ── Territory Assignments ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_territory_assignment(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, territory_id=3, user_id=7,
                    role="rep", quota=250000, current_revenue=0,
                    deal_count=0, is_primary=True,
                    assigned_at=TS, created_at=TS)
    monkeypatch.setattr(ta_svc, "create_assignment", fake)
    r = await client.post("/api/v1/territory-assignments", json={"territory_id": 3, "user_id": 7, "quota": 250000})
    assert r.status_code == 201
    assert r.json()["quota"] == 250000


@pytest.mark.asyncio
async def test_territory_coverage(client, monkeypatch):
    async def fake(db, org_id):
        return {"territories_covered": 5, "reps_assigned": 8,
                "total_quota": 2000000, "total_revenue": 950000, "attainment_pct": 47.5}
    monkeypatch.setattr(ta_svc, "get_coverage", fake)
    r = await client.get("/api/v1/territory-assignments/coverage")
    assert r.status_code == 200
    assert r.json()["territories_covered"] == 5


# ── Quote Approvals ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_approval(client, monkeypatch):
    async def fake(db, *, organization_id, requested_by_user_id, **kw):
        return _obj(id=1, organization_id=1, quote_id=10, level=1,
                    approver_user_id=2, status="pending", reason=None,
                    requested_by_user_id=1, requested_at=TS,
                    decided_at=None, created_at=TS)
    monkeypatch.setattr(qa_svc, "request_approval", fake)
    r = await client.post("/api/v1/quote-approvals", json={"quote_id": 10, "approver_user_id": 2})
    assert r.status_code == 201
    assert r.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_decide_approval(client, monkeypatch):
    async def fake(db, approval_id, org_id, status, reason):
        return _obj(id=1, organization_id=1, quote_id=10, level=1,
                    approver_user_id=2, status="approved",
                    reason="Looks good", requested_by_user_id=1,
                    requested_at=TS, decided_at=TS, created_at=TS)
    monkeypatch.setattr(qa_svc, "decide", fake)
    r = await client.put("/api/v1/quote-approvals/1/decide", json={"status": "approved", "reason": "Looks good"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_pending_count(client, monkeypatch):
    async def fake(db, org_id, approver_user_id=None):
        return {"pending_count": 5}
    monkeypatch.setattr(qa_svc, "get_pending_count", fake)
    r = await client.get("/api/v1/quote-approvals/pending")
    assert r.status_code == 200
    assert r.json()["pending_count"] == 5


# ── Win/Loss Analysis ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_outcome(client, monkeypatch):
    async def fake(db, *, organization_id, recorded_by_user_id, **kw):
        return _obj(id=1, organization_id=1, deal_id=10, outcome="won",
                    primary_reason="Best product fit",
                    secondary_reason=None, competitor_id=None,
                    deal_amount=50000, sales_cycle_days=45,
                    notes=None, recorded_by_user_id=1, created_at=TS)
    monkeypatch.setattr(wl_svc, "record_outcome", fake)
    r = await client.post("/api/v1/win-loss", json={
        "deal_id": 10, "outcome": "won", "primary_reason": "Best product fit", "deal_amount": 50000
    })
    assert r.status_code == 201
    assert r.json()["outcome"] == "won"


@pytest.mark.asyncio
async def test_win_loss_analytics(client, monkeypatch):
    async def fake(db, org_id):
        return {"won": {"count": 30, "total_amount": 1500000, "avg_cycle_days": 35.2},
                "lost": {"count": 20, "total_amount": 800000, "avg_cycle_days": 42.1},
                "win_rate": 60.0}
    monkeypatch.setattr(wl_svc, "get_analytics", fake)
    r = await client.get("/api/v1/win-loss/analytics")
    assert r.status_code == 200
    assert r.json()["win_rate"] == 60.0


@pytest.mark.asyncio
async def test_top_loss_reasons(client, monkeypatch):
    async def fake(db, org_id, outcome):
        return [{"reason": "Price too high", "count": 8}, {"reason": "Missing features", "count": 5}]
    monkeypatch.setattr(wl_svc, "get_top_reasons", fake)
    r = await client.get("/api/v1/win-loss/top-reasons/lost")
    assert r.status_code == 200
    assert r.json()[0]["reason"] == "Price too high"
