"""Cross-organization isolation tests for batch 19 and batch 20 endpoints.

For every new endpoint, create a resource under org_a, then authenticate as
org_b and verify the resource is inaccessible (404 or empty list — never 200
with org_a data).
"""
from __future__ import annotations

import pytest

from app.services import (
    call_log as cl_svc,
)
from app.services import (
    contact_merge_log as cml_svc,
)
from app.services import (
    contact_timeline_events as ct_svc,
)
from app.services import (
    conversion_funnel as cf_svc,
)
from app.services import (
    deal_dependency as dd_svc,
)
from app.services import (
    deal_split as ds_svc,
)
from app.services import (
    drip_analytics as da_svc,
)
from app.services import (
    email_warmup as ew_svc,
)
from app.services import (
    forecast_rollup as fr_svc,
)
from app.services import (
    product_bundle as pb_svc,
)
from app.services import (
    quote_approval as qa_svc,
)
from app.services import (
    revenue_goal as rg_svc,
)
from app.services import (
    territory_assignment as ta_svc,
)
from app.services import (
    win_loss_analysis as wl_svc,
)
from tests.conftest import _make_auth_headers

TS = "2026-03-10T00:00:00+00:00"

# Helpers -----------------------------------------------------------------

ORG_A = _make_auth_headers(user_id=1, email="ceo@org1.com", role="CEO", org_id=1)
ORG_B = _make_auth_headers(user_id=2, email="ceo@org2.com", role="CEO", org_id=2)


def _obj(**kw):
    class _O:
        pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


# =========================================================================
# BATCH 19
# =========================================================================


# ── Call Logs ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_log_list_isolation(client, monkeypatch):
    """Org B must not see org A's call logs."""
    async def fake_create(db, *, organization_id, user_id, **kw):
        return _obj(id=1, organization_id=1, user_id=1, contact_id=5,
                    deal_id=None, direction="outbound", duration_seconds=120,
                    outcome="completed", recording_url=None, notes="N",
                    called_at=TS, created_at=TS)

    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [fake_create]

    monkeypatch.setattr(cl_svc, "create_call", fake_create)
    monkeypatch.setattr(cl_svc, "list_calls", fake_list)

    # Create under org A
    r = await client.post("/api/v1/call-logs",
                          json={"contact_id": 5, "duration_seconds": 120, "notes": "N"},
                          headers=ORG_A)
    assert r.status_code == 201

    # List as org B — empty
    r = await client.get("/api/v1/call-logs", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_call_log_detail_isolation(client, monkeypatch):
    """Org B must not read org A's call log by ID."""
    async def fake_get(db, call_id, org_id):
        if org_id != 1:
            return None
        return _obj(id=call_id, organization_id=1, user_id=1, contact_id=5,
                    deal_id=None, direction="outbound", duration_seconds=120,
                    outcome="completed", recording_url=None, notes="N",
                    called_at=TS, created_at=TS)

    monkeypatch.setattr(cl_svc, "get_call", fake_get)
    r = await client.get("/api/v1/call-logs/1", headers=ORG_B)
    assert r.status_code == 404


# ── Drip Analytics ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_drip_events_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, campaign_id=1, step_id=1,
                     enrollment_id=1, contact_id=10, event_type="opened",
                     metadata_json=None, created_at=TS)]

    monkeypatch.setattr(da_svc, "list_events", fake_list)
    r = await client.get("/api/v1/drip-analytics/events", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# ── Deal Splits ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_split_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, deal_id):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, deal_id=10, user_id=1,
                     split_pct=60.0, split_amount=30000.0, role="primary",
                     notes=None, created_at=TS, updated_at=TS)]

    monkeypatch.setattr(ds_svc, "list_splits", fake_list)
    r = await client.get("/api/v1/deal-splits/deal/10", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# ── Contact Merge Logs ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_merge_log_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, primary_contact_id=1,
                     merged_contact_id=2, merged_by_user_id=1,
                     before_snapshot=None, after_snapshot=None,
                     fields_changed=None, status="completed", created_at=TS)]

    monkeypatch.setattr(cml_svc, "list_merges", fake_list)
    r = await client.get("/api/v1/contact-merge-logs", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_merge_log_detail_isolation(client, monkeypatch):
    async def fake_get(db, merge_id, org_id):
        if org_id != 1:
            return None
        return _obj(id=merge_id, organization_id=1, primary_contact_id=1,
                    merged_contact_id=2, merged_by_user_id=1,
                    before_snapshot=None, after_snapshot=None,
                    fields_changed=None, status="completed", created_at=TS)

    monkeypatch.setattr(cml_svc, "get_merge", fake_get)
    r = await client.get("/api/v1/contact-merge-logs/1", headers=ORG_B)
    assert r.status_code == 404


# ── Product Bundles ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bundle_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, name="Starter Pack",
                     description=None, bundle_price=499.0,
                     individual_total=650.0, discount_pct=23.2,
                     is_active=True, created_at=TS, updated_at=TS)]

    monkeypatch.setattr(pb_svc, "list_bundles", fake_list)
    r = await client.get("/api/v1/product-bundles", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_bundle_detail_isolation(client, monkeypatch):
    async def fake_get(db, bundle_id, org_id):
        if org_id != 1:
            return None
        return _obj(id=bundle_id, organization_id=1, name="Starter Pack",
                    description=None, bundle_price=499.0,
                    individual_total=650.0, discount_pct=23.2,
                    is_active=True, created_at=TS, updated_at=TS)

    monkeypatch.setattr(pb_svc, "get_bundle", fake_get)
    r = await client.get("/api/v1/product-bundles/1", headers=ORG_B)
    assert r.status_code == 404


# ── Forecast Rollups ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rollup_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, period="2026-Q1",
                     period_type="quarterly", group_by="team",
                     group_value="Sales East", committed=200000,
                     best_case=300000, pipeline=500000,
                     weighted_pipeline=250000, closed_won=150000,
                     target=400000, attainment_pct=37.5,
                     created_at=TS, updated_at=TS)]

    monkeypatch.setattr(fr_svc, "list_rollups", fake_list)
    r = await client.get("/api/v1/forecast-rollups", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_rollup_detail_isolation(client, monkeypatch):
    async def fake_get(db, rollup_id, org_id):
        if org_id != 1:
            return None
        return _obj(id=rollup_id, organization_id=1, period="2026-Q1",
                    period_type="quarterly", group_by="team",
                    group_value="Sales East", committed=200000,
                    best_case=300000, pipeline=500000,
                    weighted_pipeline=250000, closed_won=150000,
                    target=400000, attainment_pct=37.5,
                    created_at=TS, updated_at=TS)

    monkeypatch.setattr(fr_svc, "get_rollup", fake_get)
    r = await client.get("/api/v1/forecast-rollups/1", headers=ORG_B)
    assert r.status_code == 404


# ── Conversion Funnels ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_funnel_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, period="2026-03",
                     period_type="monthly", from_stage="lead",
                     to_stage="qualified", entered_count=100,
                     converted_count=40, conversion_rate=40.0,
                     avg_time_hours=48.0, median_time_hours=36.0,
                     created_at=TS, updated_at=TS)]

    monkeypatch.setattr(cf_svc, "list_funnel", fake_list)
    r = await client.get("/api/v1/conversion-funnels", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# =========================================================================
# BATCH 20
# =========================================================================


# ── Revenue Goals ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revenue_goal_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, scope="team", scope_id=5,
                     period="2026-Q1", period_type="quarterly",
                     target_amount=500000, current_amount=0, stretch_amount=600000,
                     attainment_pct=0, gap=500000, status="active",
                     created_at=TS, updated_at=TS)]

    monkeypatch.setattr(rg_svc, "list_goals", fake_list)
    r = await client.get("/api/v1/revenue-goals", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# ── Deal Dependencies ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_dependency_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, deal_id):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, deal_id=10, depends_on_deal_id=20,
                     dependency_type="blocks", is_resolved=False,
                     notes=None, created_at=TS, resolved_at=None)]

    monkeypatch.setattr(dd_svc, "list_dependencies", fake_list)
    r = await client.get("/api/v1/deal-dependencies/deal/10", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# ── Contact Timeline ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeline_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, contact_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, contact_id=5, event_type="email",
                     event_source="gmail", title="Sent follow-up",
                     description=None, entity_type=None, entity_id=None,
                     actor_user_id=1, occurred_at=TS, created_at=TS)]

    monkeypatch.setattr(ct_svc, "list_events", fake_list)
    r = await client.get("/api/v1/contact-timeline/events/5", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# ── Email Warmup ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_warmup_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, email_address="a@a.com",
                     domain="a.com", daily_limit=5, current_daily=0,
                     target_daily=50, ramp_increment=2, warmup_day=1,
                     reputation_score=50, is_active=True,
                     started_at=TS, created_at=TS, updated_at=TS)]

    monkeypatch.setattr(ew_svc, "list_warmups", fake_list)
    r = await client.get("/api/v1/email-warmup", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# ── Territory Assignments ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_territory_assignment_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, territory_id=3, user_id=7,
                     role="rep", quota=250000, current_revenue=0,
                     deal_count=0, is_primary=True,
                     assigned_at=TS, created_at=TS)]

    monkeypatch.setattr(ta_svc, "list_assignments", fake_list)
    r = await client.get("/api/v1/territory-assignments", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# ── Quote Approvals ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quote_approval_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, quote_id=10, level=1,
                     approver_user_id=2, status="pending", reason=None,
                     requested_by_user_id=1, requested_at=TS,
                     decided_at=None, created_at=TS)]

    monkeypatch.setattr(qa_svc, "list_approvals", fake_list)
    r = await client.get("/api/v1/quote-approvals", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


# ── Win/Loss Analysis ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_win_loss_list_isolation(client, monkeypatch):
    async def fake_list(db, org_id, **kw):
        if org_id == 2:
            return []
        return [_obj(id=1, organization_id=1, deal_id=10, outcome="won",
                     primary_reason="Best product fit",
                     secondary_reason=None, competitor_id=None,
                     deal_amount=50000, sales_cycle_days=45,
                     notes=None, recorded_by_user_id=1, created_at=TS)]

    monkeypatch.setattr(wl_svc, "list_records", fake_list)
    r = await client.get("/api/v1/win-loss", headers=ORG_B)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_win_loss_detail_isolation(client, monkeypatch):
    async def fake_get(db, record_id, org_id):
        if org_id != 1:
            return None
        return _obj(id=record_id, organization_id=1, deal_id=10, outcome="won",
                    primary_reason="Best product fit",
                    secondary_reason=None, competitor_id=None,
                    deal_amount=50000, sales_cycle_days=45,
                    notes=None, recorded_by_user_id=1, created_at=TS)

    monkeypatch.setattr(wl_svc, "get_record", fake_get)
    r = await client.get("/api/v1/win-loss/1", headers=ORG_B)
    assert r.status_code == 404
