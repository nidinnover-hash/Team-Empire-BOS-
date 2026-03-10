"""Tests for idempotent upsert behavior in forecast_rollup and conversion_funnel."""
from __future__ import annotations

import pytest

from app.services import forecast_rollup as fr_svc
from app.services import conversion_funnel as cf_svc


# ── Forecast Rollup ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forecast_rollup_upsert_creates_new_row(db):
    row = await fr_svc.upsert_rollup(
        db, organization_id=1, period="2026-Q1", period_type="quarterly",
        group_by="team", group_value="Sales", committed=100, best_case=120,
        pipeline=150, weighted_pipeline=110, closed_won=70, target=200, attainment_pct=35,
    )
    assert row.id is not None
    assert row.committed == 100


@pytest.mark.asyncio
async def test_forecast_rollup_upsert_updates_existing_by_natural_key(db):
    first = await fr_svc.upsert_rollup(
        db, organization_id=1, period="2026-Q2", period_type="quarterly",
        group_by="team", group_value="Engineering", committed=50, best_case=60,
        pipeline=80, weighted_pipeline=55, closed_won=30, target=100, attainment_pct=30,
    )
    second = await fr_svc.upsert_rollup(
        db, organization_id=1, period="2026-Q2", period_type="quarterly",
        group_by="team", group_value="Engineering", committed=130, best_case=150,
        pipeline=180, weighted_pipeline=140, closed_won=90, target=200, attainment_pct=45,
    )
    assert second.id == first.id
    assert second.committed == 130
    assert second.attainment_pct == 45


@pytest.mark.asyncio
async def test_forecast_rollup_no_duplicate_rows_after_upsert(db):
    await fr_svc.upsert_rollup(
        db, organization_id=1, period="2026-Q3", period_type="quarterly",
        group_by="region", group_value="APAC", committed=200, best_case=220,
        pipeline=300, weighted_pipeline=210, closed_won=150, target=400, attainment_pct=37.5,
    )
    await fr_svc.upsert_rollup(
        db, organization_id=1, period="2026-Q3", period_type="quarterly",
        group_by="region", group_value="APAC", committed=250, best_case=270,
        pipeline=350, weighted_pipeline=260, closed_won=200, target=400, attainment_pct=50,
    )
    rows = await fr_svc.list_rollups(db, org_id=1, period="2026-Q3", group_by="region")
    apac = [r for r in rows if r.group_value == "APAC"]
    assert len(apac) == 1


@pytest.mark.asyncio
async def test_forecast_rollup_different_natural_key_creates_separate_row(db):
    await fr_svc.upsert_rollup(
        db, organization_id=1, period="2026-Q4", period_type="quarterly",
        group_by="team", group_value="Sales", committed=100, best_case=100,
        pipeline=100, weighted_pipeline=100, closed_won=100, target=100, attainment_pct=100,
    )
    await fr_svc.upsert_rollup(
        db, organization_id=1, period="2026-Q4", period_type="quarterly",
        group_by="team", group_value="Marketing", committed=50, best_case=50,
        pipeline=50, weighted_pipeline=50, closed_won=50, target=50, attainment_pct=100,
    )
    rows = await fr_svc.list_rollups(db, org_id=1, period="2026-Q4", group_by="team")
    assert len(rows) == 2


# ── Conversion Funnel ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversion_funnel_upsert_creates_new_row(db):
    row = await cf_svc.upsert_stage(
        db, organization_id=1, period="2026-03", period_type="monthly",
        from_stage="Lead", to_stage="Qualified", entered_count=100, converted_count=60,
        conversion_rate=60.0, avg_time_hours=48.0, median_time_hours=36.0,
    )
    assert row.id is not None
    assert row.entered_count == 100


@pytest.mark.asyncio
async def test_conversion_funnel_upsert_updates_existing(db):
    first = await cf_svc.upsert_stage(
        db, organization_id=1, period="2026-04", period_type="monthly",
        from_stage="Qualified", to_stage="Proposal", entered_count=50, converted_count=25,
        conversion_rate=50.0, avg_time_hours=72.0, median_time_hours=60.0,
    )
    second = await cf_svc.upsert_stage(
        db, organization_id=1, period="2026-04", period_type="monthly",
        from_stage="Qualified", to_stage="Proposal", entered_count=80, converted_count=45,
        conversion_rate=56.25, avg_time_hours=65.0, median_time_hours=55.0,
    )
    assert second.id == first.id
    assert second.entered_count == 80
    assert second.conversion_rate == 56.25


@pytest.mark.asyncio
async def test_conversion_funnel_no_duplicates(db):
    await cf_svc.upsert_stage(
        db, organization_id=1, period="2026-05", period_type="monthly",
        from_stage="Proposal", to_stage="Closed", entered_count=30, converted_count=10,
        conversion_rate=33.3, avg_time_hours=120.0, median_time_hours=96.0,
    )
    await cf_svc.upsert_stage(
        db, organization_id=1, period="2026-05", period_type="monthly",
        from_stage="Proposal", to_stage="Closed", entered_count=35, converted_count=15,
        conversion_rate=42.8, avg_time_hours=110.0, median_time_hours=90.0,
    )
    rows = await cf_svc.list_funnel(db, org_id=1, period="2026-05")
    proposal_closed = [r for r in rows if r.from_stage == "Proposal" and r.to_stage == "Closed"]
    assert len(proposal_closed) == 1
