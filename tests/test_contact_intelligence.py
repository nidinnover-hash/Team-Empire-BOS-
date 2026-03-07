"""Tests for Contact Intelligence — scoring, stale detection, follow-up suggestions."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import _make_auth_headers


# ── score_contact ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_contact_new():
    from app.models.contact import Contact
    from app.services.contact_intelligence import score_contact

    c = Contact(
        organization_id=1, name="Test", pipeline_stage="new",
        lead_score=0,
    )
    score = await score_contact(c)
    assert 0 <= score <= 100
    assert score == 5  # new stage = 5, nothing else


@pytest.mark.asyncio
async def test_score_contact_with_activity():
    from app.models.contact import Contact
    from app.services.contact_intelligence import score_contact

    c = Contact(
        organization_id=1, name="Active Lead",
        pipeline_stage="qualified",
        email="test@test.com", phone="+123",
        deal_value=5000.0,
        last_contacted_at=datetime.now(UTC) - timedelta(days=2),
        next_follow_up_at=datetime.now(UTC) + timedelta(days=3),
        qualified_status="qualified",
        lead_score=0,
    )
    score = await score_contact(c)
    # qualified(30) + email(5) + phone(5) + deal(10) + recent(10) + followup(5) + qualified(10) = 75
    assert score == 75


@pytest.mark.asyncio
async def test_score_contact_disqualified():
    from app.models.contact import Contact
    from app.services.contact_intelligence import score_contact

    c = Contact(
        organization_id=1, name="Disq",
        pipeline_stage="new",
        qualified_status="disqualified",
        lead_score=0,
    )
    score = await score_contact(c)
    # new(5) + disqualified(-20) = 0 (clamped)
    assert score == 0


# ── batch_score_contacts ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_score_contacts(db):
    from app.models.contact import Contact
    from app.services.contact_intelligence import batch_score_contacts

    c = Contact(
        organization_id=1, name="Batch Score Test",
        pipeline_stage="proposal", email="batch@test.com",
        lead_score=0,
    )
    db.add(c)
    await db.flush()

    result = await batch_score_contacts(db, organization_id=1, limit=500)
    assert result["total_scored"] >= 1
    assert isinstance(result["updated"], int)


# ── get_stale_contacts ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_contacts_empty(db):
    from app.services.contact_intelligence import get_stale_contacts

    result = await get_stale_contacts(db, organization_id=9999)
    assert result == []


@pytest.mark.asyncio
async def test_stale_contacts_finds_old(db):
    from app.models.contact import Contact
    from app.services.contact_intelligence import get_stale_contacts

    c = Contact(
        organization_id=1, name="Stale Contact",
        pipeline_stage="contacted",
        last_contacted_at=datetime.now(UTC) - timedelta(days=60),
        lead_score=20,
    )
    db.add(c)
    await db.flush()

    result = await get_stale_contacts(db, organization_id=1, stale_days=30)
    stale_names = [s["name"] for s in result]
    assert "Stale Contact" in stale_names


@pytest.mark.asyncio
async def test_stale_contacts_excludes_won(db):
    from app.models.contact import Contact
    from app.services.contact_intelligence import get_stale_contacts

    c = Contact(
        organization_id=1, name="Won Contact",
        pipeline_stage="won",
        last_contacted_at=datetime.now(UTC) - timedelta(days=60),
        lead_score=90,
    )
    db.add(c)
    await db.flush()

    result = await get_stale_contacts(db, organization_id=1, stale_days=30)
    stale_names = [s["name"] for s in result]
    assert "Won Contact" not in stale_names


# ── get_follow_up_suggestions ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_follow_up_overdue(db):
    from app.models.contact import Contact
    from app.services.contact_intelligence import get_follow_up_suggestions

    c = Contact(
        organization_id=1, name="Overdue Follow-up",
        pipeline_stage="proposal",
        next_follow_up_at=datetime.now(UTC) - timedelta(days=5),
        lead_score=60,
    )
    db.add(c)
    await db.flush()

    result = await get_follow_up_suggestions(db, organization_id=1)
    overdue = [s for s in result if s["name"] == "Overdue Follow-up"]
    assert len(overdue) >= 1
    assert overdue[0]["reason"] == "overdue_follow_up"


@pytest.mark.asyncio
async def test_follow_up_high_score_no_followup(db):
    from app.models.contact import Contact
    from app.services.contact_intelligence import get_follow_up_suggestions

    c = Contact(
        organization_id=1, name="High Score No FU",
        pipeline_stage="qualified",
        next_follow_up_at=None,
        lead_score=50,
    )
    db.add(c)
    await db.flush()

    result = await get_follow_up_suggestions(db, organization_id=1)
    high_score = [s for s in result if s["name"] == "High Score No FU"]
    assert len(high_score) >= 1
    assert high_score[0]["reason"] == "high_score_no_follow_up"


# ── get_pipeline_analytics ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_analytics(db):
    from app.services.contact_intelligence import get_pipeline_analytics

    result = await get_pipeline_analytics(db, organization_id=1)
    assert "total_contacts" in result
    assert "stages" in result
    assert isinstance(result["stages"], list)


# ── get_contact_intelligence_summary ────────────────────────────────────────

@pytest.mark.asyncio
async def test_intelligence_summary_structure(db):
    from app.services.contact_intelligence import get_contact_intelligence_summary

    result = await get_contact_intelligence_summary(db, organization_id=1)
    assert "pipeline" in result
    assert "stale_contacts" in result
    assert "follow_up_suggestions" in result
    assert "stale_count" in result
    assert "follow_up_count" in result


# ── API endpoints ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_intelligence_endpoint(client):
    headers = _make_auth_headers()
    r = await client.get("/api/v1/contacts/intelligence", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "pipeline" in data
    assert "stale_contacts" in data


@pytest.mark.asyncio
async def test_rescore_endpoint(client):
    headers = _make_auth_headers()
    r = await client.post("/api/v1/contacts/intelligence/rescore", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "total_scored" in data
    assert "updated" in data
