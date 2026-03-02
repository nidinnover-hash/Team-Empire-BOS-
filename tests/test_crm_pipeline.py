"""Tests for CRM pipeline features: create with CRM fields, filter, pipeline summary, follow-up due."""

# ── Contact CRM Fields ──────────────────────────────────────────────────────


async def test_create_contact_with_pipeline_fields(client):
    response = await client.post(
        "/api/v1/contacts",
        json={
            "name": "Lead A",
            "email": "lead@example.com",
            "pipeline_stage": "qualified",
            "lead_score": 80,
            "lead_source": "referral",
            "deal_value": 50000.0,
            "tags": "enterprise,priority",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["pipeline_stage"] == "qualified"
    assert body["lead_score"] == 80
    assert body["lead_source"] == "referral"
    assert body["deal_value"] == 50000.0
    assert body["tags"] == "enterprise,priority"


async def test_create_contact_defaults_pipeline_stage(client):
    response = await client.post("/api/v1/contacts", json={"name": "Default Lead"})
    assert response.status_code == 201
    body = response.json()
    assert body["pipeline_stage"] == "new"
    assert body["lead_score"] == 0
    assert body["deal_value"] is None


async def test_update_contact_pipeline_fields(client):
    create_resp = await client.post("/api/v1/contacts", json={"name": "Update Me"})
    contact_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/contacts/{contact_id}",
        json={"pipeline_stage": "proposal", "lead_score": 65, "deal_value": 10000},
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["pipeline_stage"] == "proposal"
    assert body["lead_score"] == 65
    assert body["deal_value"] == 10000.0


# ── Filtering ────────────────────────────────────────────────────────────────


async def test_list_contacts_filter_by_pipeline_stage(client):
    await client.post("/api/v1/contacts", json={"name": "New Lead", "pipeline_stage": "new"})
    await client.post("/api/v1/contacts", json={"name": "Won Lead", "pipeline_stage": "won"})

    resp = await client.get("/api/v1/contacts?pipeline_stage=won")
    assert resp.status_code == 200
    items = resp.json()
    assert all(c["pipeline_stage"] == "won" for c in items)
    assert any(c["name"] == "Won Lead" for c in items)


async def test_list_contacts_filter_by_score_range(client):
    await client.post("/api/v1/contacts", json={"name": "Low Score", "lead_score": 10})
    await client.post("/api/v1/contacts", json={"name": "High Score", "lead_score": 90})

    resp = await client.get("/api/v1/contacts?lead_score_min=50")
    items = resp.json()
    assert all(c["lead_score"] >= 50 for c in items)


async def test_list_contacts_search(client):
    await client.post("/api/v1/contacts", json={"name": "Alice Findme", "company": "Acme"})
    await client.post("/api/v1/contacts", json={"name": "Bob Hidden"})

    resp = await client.get("/api/v1/contacts?search=Findme")
    items = resp.json()
    assert any(c["name"] == "Alice Findme" for c in items)
    assert not any(c["name"] == "Bob Hidden" for c in items)


# ── Pipeline Summary ─────────────────────────────────────────────────────────


async def test_pipeline_summary_returns_all_stages(client):
    await client.post("/api/v1/contacts", json={"name": "Won Deal", "pipeline_stage": "won", "deal_value": 5000})
    await client.post("/api/v1/contacts", json={"name": "New Lead", "pipeline_stage": "new"})

    resp = await client.get("/api/v1/contacts/pipeline-summary")
    assert resp.status_code == 200
    data = resp.json()
    stages = {s["stage"] for s in data}
    assert stages == {"new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"}

    won = next(s for s in data if s["stage"] == "won")
    assert won["count"] >= 1
    assert won["total_deal_value"] >= 5000


async def test_pipeline_summary_empty_org(client):
    """Pipeline summary works even with no contacts."""
    resp = await client.get("/api/v1/contacts/pipeline-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 7  # all 7 stages


# ── Follow-Up Due ────────────────────────────────────────────────────────────


async def test_follow_up_due_returns_due_contacts(client):
    from datetime import UTC, datetime, timedelta

    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    await client.post("/api/v1/contacts", json={"name": "Due Contact"})

    # Get the contact and set follow-up in the past via PATCH
    contacts = (await client.get("/api/v1/contacts")).json()
    contact_id = next(c["id"] for c in contacts if c["name"] == "Due Contact")

    await client.patch(
        f"/api/v1/contacts/{contact_id}",
        json={"next_follow_up_at": past},
    )

    resp = await client.get("/api/v1/contacts/follow-up-due")
    assert resp.status_code == 200
    items = resp.json()
    assert any(c["name"] == "Due Contact" for c in items)


async def test_follow_up_due_excludes_future(client):
    from datetime import UTC, datetime, timedelta

    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    await client.post("/api/v1/contacts", json={"name": "Future Contact"})

    contacts = (await client.get("/api/v1/contacts")).json()
    contact_id = next(c["id"] for c in contacts if c["name"] == "Future Contact")

    await client.patch(
        f"/api/v1/contacts/{contact_id}",
        json={"next_follow_up_at": future},
    )

    resp = await client.get("/api/v1/contacts/follow-up-due")
    items = resp.json()
    assert not any(c["name"] == "Future Contact" for c in items)
