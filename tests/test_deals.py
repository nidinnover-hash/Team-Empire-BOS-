"""Tests for Deal CRUD and pipeline analytics."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_deal(client):
    """Create a deal and verify fields."""
    resp = await client.post("/api/v1/deals", json={
        "title": "Big Partnership", "value": 50000.0, "stage": "discovery",
        "probability": 30, "description": "Enterprise deal",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Big Partnership"
    assert data["value"] == 50000.0
    assert data["stage"] == "discovery"
    assert data["probability"] == 30
    assert data["owner_user_id"] is not None


@pytest.mark.asyncio
async def test_list_deals(client):
    """List deals returns created deals."""
    await client.post("/api/v1/deals", json={"title": "Deal A", "value": 1000.0})
    await client.post("/api/v1/deals", json={"title": "Deal B", "value": 2000.0})

    resp = await client.get("/api/v1/deals")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_list_deals_by_stage(client):
    """Filter deals by stage."""
    await client.post("/api/v1/deals", json={"title": "Prop Deal", "stage": "proposal"})
    await client.post("/api/v1/deals", json={"title": "Won Deal", "stage": "won"})

    resp = await client.get("/api/v1/deals?stage=proposal")
    deals = resp.json()
    assert all(d["stage"] == "proposal" for d in deals)


@pytest.mark.asyncio
async def test_update_deal_stage(client):
    """Updating stage to won sets won_at timestamp."""
    r = await client.post("/api/v1/deals", json={"title": "Close Me", "value": 5000.0})
    deal_id = r.json()["id"]

    resp = await client.patch(f"/api/v1/deals/{deal_id}", json={"stage": "won"})
    assert resp.status_code == 200
    assert resp.json()["stage"] == "won"
    assert resp.json()["won_at"] is not None


@pytest.mark.asyncio
async def test_update_deal_lost(client):
    """Updating stage to lost sets lost_at and accepts lost_reason."""
    r = await client.post("/api/v1/deals", json={"title": "Lose Me"})
    deal_id = r.json()["id"]

    resp = await client.patch(f"/api/v1/deals/{deal_id}", json={
        "stage": "lost", "lost_reason": "Budget cut",
    })
    assert resp.json()["stage"] == "lost"
    assert resp.json()["lost_at"] is not None
    assert resp.json()["lost_reason"] == "Budget cut"


@pytest.mark.asyncio
async def test_delete_deal(client):
    """Delete a deal."""
    r = await client.post("/api/v1/deals", json={"title": "Temp Deal"})
    deal_id = r.json()["id"]

    resp = await client.delete(f"/api/v1/deals/{deal_id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/deals/{deal_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_deal_with_contact(client):
    """Deal can be linked to a contact."""
    c = await client.post("/api/v1/contacts", json={
        "name": "Deal Contact", "relationship": "business",
    })
    contact_id = c.json()["id"]

    resp = await client.post("/api/v1/deals", json={
        "title": "Contact Deal", "contact_id": contact_id, "value": 10000.0,
    })
    assert resp.status_code == 201
    assert resp.json()["contact_id"] == contact_id

    # Filter by contact_id
    list_resp = await client.get(f"/api/v1/deals?contact_id={contact_id}")
    assert len(list_resp.json()) >= 1


@pytest.mark.asyncio
async def test_deal_summary(client):
    """Deal summary returns pipeline analytics."""
    await client.post("/api/v1/deals", json={"title": "D1", "value": 1000.0, "stage": "discovery"})
    await client.post("/api/v1/deals", json={"title": "D2", "value": 5000.0, "stage": "won"})
    await client.post("/api/v1/deals", json={"title": "D3", "value": 2000.0, "stage": "lost"})

    resp = await client.get("/api/v1/deals/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_deals"] >= 3
    assert data["won_value"] >= 5000.0
    assert data["lost_count"] >= 1
    assert "pipeline" in data
