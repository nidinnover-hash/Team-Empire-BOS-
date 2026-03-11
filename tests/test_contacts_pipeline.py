"""Tests for contact deduplication, merge, and pipeline analytics."""
from __future__ import annotations

import pytest

# ── Duplicate detection ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_duplicates_by_email(client):
    """Contacts with the same email appear as duplicate group."""
    # Create two contacts with same email
    await client.post("/api/v1/contacts", json={
        "name": "Alice A", "email": "alice@example.com", "relationship": "business",
    })
    await client.post("/api/v1/contacts", json={
        "name": "Alice B", "email": "alice@example.com", "relationship": "business",
    })

    resp = await client.get("/api/v1/contacts/duplicates")
    assert resp.status_code == 200
    groups = resp.json()
    email_groups = [g for g in groups if g["match_field"] == "email" and g["match_value"] == "alice@example.com"]
    assert len(email_groups) >= 1
    assert email_groups[0]["count"] == 2


@pytest.mark.asyncio
async def test_find_duplicates_by_phone(client):
    """Contacts with the same phone appear as duplicate group."""
    await client.post("/api/v1/contacts", json={
        "name": "Bob A", "phone": "+1234567890", "relationship": "business",
    })
    await client.post("/api/v1/contacts", json={
        "name": "Bob B", "phone": "+1234567890", "relationship": "business",
    })

    resp = await client.get("/api/v1/contacts/duplicates")
    assert resp.status_code == 200
    groups = resp.json()
    phone_groups = [g for g in groups if g["match_field"] == "phone" and g["match_value"] == "+1234567890"]
    assert len(phone_groups) >= 1


@pytest.mark.asyncio
async def test_no_duplicates_returns_empty(client):
    """Unique contacts yield no duplicates."""
    await client.post("/api/v1/contacts", json={
        "name": "Unique One", "email": "u1@test.com", "relationship": "business",
    })
    await client.post("/api/v1/contacts", json={
        "name": "Unique Two", "email": "u2@test.com", "relationship": "business",
    })

    resp = await client.get("/api/v1/contacts/duplicates")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Merge ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_merge_contacts_fills_blanks(client):
    """Merge fills in null fields on the primary from duplicates."""
    c1 = await client.post("/api/v1/contacts", json={
        "name": "Primary", "email": "merge@test.com", "relationship": "business",
    })
    c2 = await client.post("/api/v1/contacts", json={
        "name": "Dupe", "phone": "+9876543210", "company": "MergeCorp", "relationship": "business",
    })
    primary_id = c1.json()["id"]
    dupe_id = c2.json()["id"]

    resp = await client.post("/api/v1/contacts/merge", json={
        "primary_id": primary_id, "duplicate_ids": [dupe_id],
    })
    assert resp.status_code == 200
    merged = resp.json()
    assert merged["id"] == primary_id
    assert merged["email"] == "merge@test.com"
    assert merged["phone"] == "+9876543210"
    assert merged["company"] == "MergeCorp"

    # Duplicate should be gone
    get_resp = await client.get(f"/api/v1/contacts/{dupe_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_merge_keeps_highest_lead_score(client):
    """Merge takes the highest lead_score."""
    c1 = await client.post("/api/v1/contacts", json={
        "name": "Low Score", "email": "score@test.com", "relationship": "business",
    })
    # Patch lead_score directly via update
    c1_id = c1.json()["id"]

    c2 = await client.post("/api/v1/contacts", json={
        "name": "High Score", "email": "score2@test.com", "relationship": "business",
    })
    c2_id = c2.json()["id"]
    # Update lead_score via qualify endpoint if available, otherwise just check merge logic
    await client.patch(f"/api/v1/contacts/{c2_id}", json={"lead_score": 85})

    resp = await client.post("/api/v1/contacts/merge", json={
        "primary_id": c1_id, "duplicate_ids": [c2_id],
    })
    assert resp.status_code == 200
    assert resp.json()["lead_score"] >= 85


@pytest.mark.asyncio
async def test_merge_nonexistent_primary_returns_404(client):
    """Merging into a nonexistent primary returns 404."""
    resp = await client.post("/api/v1/contacts/merge", json={
        "primary_id": 99999, "duplicate_ids": [1],
    })
    assert resp.status_code == 404


# ── Pipeline analytics ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_analytics_returns_funnel(client):
    """Pipeline analytics returns a funnel with expected stages."""
    # Create contacts in different stages
    for stage in ("new", "contacted", "qualified", "won"):
        await client.post("/api/v1/contacts", json={
            "name": f"Contact {stage}", "pipeline_stage": stage, "relationship": "business",
        })

    resp = await client.get("/api/v1/contacts/pipeline-analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert "funnel" in data
    assert "total_contacts" in data
    assert "win_rate" in data
    assert data["total_contacts"] >= 4

    stages = [s["stage"] for s in data["funnel"]]
    assert "new" in stages
    assert "won" in stages


@pytest.mark.asyncio
async def test_pipeline_analytics_empty(client):
    """Pipeline analytics works with zero contacts."""
    resp = await client.get("/api/v1/contacts/pipeline-analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_contacts"] == 0
    assert data["win_rate"] == 0.0
