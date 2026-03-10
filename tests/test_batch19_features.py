"""Tests for batch 19: call logs, drip analytics, deal splits,
contact merge logs, product bundles, forecast rollups, conversion funnels."""
from __future__ import annotations

import pytest

from app.services import (
    call_log as cl_svc,
    drip_analytics as da_svc,
    deal_split as ds_svc,
    contact_merge_log as cml_svc,
    product_bundle as pb_svc,
    forecast_rollup as fr_svc,
    conversion_funnel as cf_svc,
)


def _obj(**kw):
    class _O: pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


TS = "2026-03-10T00:00:00+00:00"


# ── Call Logs ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_call(client, monkeypatch):
    async def fake(db, *, organization_id, user_id, **kw):
        return _obj(id=1, organization_id=1, user_id=1, contact_id=5,
                    deal_id=None, direction="outbound", duration_seconds=120,
                    outcome="completed", recording_url=None, notes="Follow up",
                    called_at=TS, created_at=TS)
    monkeypatch.setattr(cl_svc, "create_call", fake)
    r = await client.post("/api/v1/call-logs", json={"contact_id": 5, "duration_seconds": 120, "notes": "Follow up"})
    assert r.status_code == 201
    assert r.json()["duration_seconds"] == 120


@pytest.mark.asyncio
async def test_call_stats(client, monkeypatch):
    async def fake(db, org_id, user_id=None):
        return {"total_calls": 50, "total_duration": 6000, "avg_duration": 120.0}
    monkeypatch.setattr(cl_svc, "get_stats", fake)
    r = await client.get("/api/v1/call-logs/stats")
    assert r.status_code == 200
    assert r.json()["total_calls"] == 50


# ── Drip Analytics ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_drip_event(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, campaign_id=1, step_id=1,
                    enrollment_id=1, contact_id=10, event_type="opened",
                    metadata_json=None, created_at=TS)
    monkeypatch.setattr(da_svc, "record_event", fake)
    r = await client.post("/api/v1/drip-analytics/events", json={
        "campaign_id": 1, "step_id": 1, "enrollment_id": 1,
        "contact_id": 10, "event_type": "opened"
    })
    assert r.status_code == 201
    assert r.json()["event_type"] == "opened"


@pytest.mark.asyncio
async def test_drip_campaign_summary(client, monkeypatch):
    async def fake(db, org_id, campaign_id):
        return {"sent": 100, "opened": 40, "clicked": 10, "bounced": 5,
                "unsubscribed": 2, "open_rate": 40.0, "click_rate": 10.0, "bounce_rate": 5.0}
    monkeypatch.setattr(da_svc, "get_campaign_summary", fake)
    r = await client.get("/api/v1/drip-analytics/summary/1")
    assert r.status_code == 200
    assert r.json()["open_rate"] == 40.0


# ── Deal Splits ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_split(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, deal_id=10, user_id=1,
                    split_pct=60.0, split_amount=30000.0, role="primary",
                    notes=None, created_at=TS, updated_at=TS)
    monkeypatch.setattr(ds_svc, "create_split", fake)
    r = await client.post("/api/v1/deal-splits", json={"deal_id": 10, "user_id": 1, "split_pct": 60.0, "split_amount": 30000})
    assert r.status_code == 201
    assert r.json()["split_pct"] == 60.0


@pytest.mark.asyncio
async def test_split_summary(client, monkeypatch):
    async def fake(db, org_id, deal_id):
        return {"deal_id": 10, "split_count": 2, "total_pct": 100.0, "total_amount": 50000.0, "is_valid": True}
    monkeypatch.setattr(ds_svc, "get_summary", fake)
    r = await client.get("/api/v1/deal-splits/deal/10/summary")
    assert r.status_code == 200
    assert r.json()["is_valid"] is True


# ── Contact Merge Logs ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_merge(client, monkeypatch):
    async def fake(db, *, organization_id, merged_by_user_id, **kw):
        return _obj(id=1, organization_id=1, primary_contact_id=1,
                    merged_contact_id=2, merged_by_user_id=1,
                    before_snapshot=None, after_snapshot=None,
                    fields_changed=None, status="completed", created_at=TS)
    monkeypatch.setattr(cml_svc, "record_merge", fake)
    r = await client.post("/api/v1/contact-merge-logs", json={"primary_contact_id": 1, "merged_contact_id": 2})
    assert r.status_code == 201
    assert r.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_merge_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"total": 15, "completed": 13, "reverted": 2}
    monkeypatch.setattr(cml_svc, "get_stats", fake)
    r = await client.get("/api/v1/contact-merge-logs/stats")
    assert r.status_code == 200
    assert r.json()["total"] == 15


# ── Product Bundles ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_bundle(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Starter Pack",
                    description=None, bundle_price=499.0,
                    individual_total=650.0, discount_pct=23.2,
                    is_active=True, created_at=TS, updated_at=TS)
    monkeypatch.setattr(pb_svc, "create_bundle", fake)
    r = await client.post("/api/v1/product-bundles", json={"name": "Starter Pack", "bundle_price": 499})
    assert r.status_code == 201
    assert r.json()["name"] == "Starter Pack"


@pytest.mark.asyncio
async def test_add_bundle_item(client, monkeypatch):
    async def fake(db, bundle_id, org_id, **kw):
        return _obj(id=1, bundle_id=1, product_id=5, quantity=2, unit_price=100.0)
    monkeypatch.setattr(pb_svc, "add_item", fake)
    r = await client.post("/api/v1/product-bundles/1/items", json={"product_id": 5, "quantity": 2, "unit_price": 100})
    assert r.status_code == 201
    assert r.json()["quantity"] == 2


@pytest.mark.asyncio
async def test_bundle_pricing(client, monkeypatch):
    async def fake(db, bundle_id, org_id):
        return {"bundle_id": 1, "bundle_price": 499.0, "individual_total": 650.0,
                "savings": 151.0, "discount_pct": 23.2, "item_count": 3}
    monkeypatch.setattr(pb_svc, "get_pricing", fake)
    r = await client.get("/api/v1/product-bundles/1/pricing")
    assert r.status_code == 200
    assert r.json()["savings"] == 151.0


# ── Forecast Rollups ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_rollup(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, period="2026-Q1",
                    period_type="quarterly", group_by="team",
                    group_value="Sales East", committed=200000,
                    best_case=300000, pipeline=500000,
                    weighted_pipeline=250000, closed_won=150000,
                    target=400000, attainment_pct=37.5,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(fr_svc, "upsert_rollup", fake)
    r = await client.post("/api/v1/forecast-rollups", json={
        "period": "2026-Q1", "period_type": "quarterly",
        "group_value": "Sales East", "committed": 200000, "target": 400000
    })
    assert r.status_code == 201
    assert r.json()["attainment_pct"] == 37.5


@pytest.mark.asyncio
async def test_period_summary(client, monkeypatch):
    async def fake(db, org_id, period):
        return {"period": "2026-Q1", "total_committed": 500000,
                "total_best_case": 700000, "total_pipeline": 1200000,
                "total_closed_won": 350000, "total_target": 800000,
                "overall_attainment": 43.8}
    monkeypatch.setattr(fr_svc, "get_period_summary", fake)
    r = await client.get("/api/v1/forecast-rollups/summary/2026-Q1")
    assert r.status_code == 200
    assert r.json()["overall_attainment"] == 43.8


# ── Conversion Funnels ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_funnel_stage(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, period="2026-03",
                    period_type="monthly", from_stage="lead",
                    to_stage="qualified", entered_count=100,
                    converted_count=40, conversion_rate=40.0,
                    avg_time_hours=48.0, median_time_hours=36.0,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(cf_svc, "upsert_stage", fake)
    r = await client.post("/api/v1/conversion-funnels", json={
        "period": "2026-03", "from_stage": "lead", "to_stage": "qualified",
        "entered_count": 100, "converted_count": 40, "conversion_rate": 40.0
    })
    assert r.status_code == 201
    assert r.json()["conversion_rate"] == 40.0


@pytest.mark.asyncio
async def test_funnel_summary(client, monkeypatch):
    async def fake(db, org_id, period):
        return {"period": "2026-03", "stages": [
            {"from_stage": "lead", "to_stage": "qualified", "entered": 100,
             "converted": 40, "rate": 40.0, "avg_time_hours": 48.0}
        ], "overall_conversion": 15.0}
    monkeypatch.setattr(cf_svc, "get_funnel_summary", fake)
    r = await client.get("/api/v1/conversion-funnels/summary/2026-03")
    assert r.status_code == 200
    assert r.json()["overall_conversion"] == 15.0


@pytest.mark.asyncio
async def test_funnel_bottlenecks(client, monkeypatch):
    async def fake(db, org_id, period):
        return [{"from_stage": "proposal", "to_stage": "negotiation",
                 "conversion_rate": 30.0, "avg_time_hours": 120.0, "drop_off": 14}]
    monkeypatch.setattr(cf_svc, "get_bottlenecks", fake)
    r = await client.get("/api/v1/conversion-funnels/bottlenecks/2026-03")
    assert r.status_code == 200
    assert r.json()[0]["conversion_rate"] == 30.0
