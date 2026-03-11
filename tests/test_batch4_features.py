"""Tests for batch 4 features: deal forecast, integration health page,
contact enrichment, goal-to-project linking, audit log enhancements."""

import pytest
from httpx import AsyncClient

# ── Deal Revenue Forecasting ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_forecast_empty(client: AsyncClient):
    """Forecast with no deals returns valid structure."""
    r = await client.get("/api/v1/deals/forecast")
    assert r.status_code == 200
    body = r.json()
    assert "months" in body
    assert "total_weighted" in body
    assert "total_unweighted" in body
    assert "open_deals" in body
    assert body["open_deals"] == 0


@pytest.mark.asyncio
async def test_deal_forecast_with_deal(client: AsyncClient):
    """Forecast includes open deal value."""
    # Create a deal
    deal_data = {
        "title": "Forecast Test Deal",
        "value": 10000,
        "stage": "proposal",
        "probability": 50,
    }
    cr = await client.post("/api/v1/deals", json=deal_data)
    assert cr.status_code == 201

    r = await client.get("/api/v1/deals/forecast")
    assert r.status_code == 200
    body = r.json()
    assert body["open_deals"] >= 1
    assert body["total_unweighted"] == pytest.approx(10000.0, rel=0.01)
    assert body["total_weighted"] == pytest.approx(5000.0, rel=0.01)


@pytest.mark.asyncio
async def test_deal_forecast_months_param(client: AsyncClient):
    """Forecast respects months parameter."""
    r = await client.get("/api/v1/deals/forecast?months=3")
    assert r.status_code == 200
    assert len(r.json()["months"]) == 3


# ── Integration Health Page ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_integration_health_page_redirect(client: AsyncClient):
    """Integration health page redirects to login without session cookie."""
    from httpx import ASGITransport
    from httpx import AsyncClient as AC

    from app.main import app

    async with AC(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as anon:
        r = await anon.get("/web/integration-health")
        assert r.status_code in (302, 303, 307)


# ── Contact Enrichment ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_enrichment_extract_domain():
    """_extract_domain extracts domain from email."""
    from app.services.contact_enrichment import _extract_domain
    assert _extract_domain("user@example.com") == "example.com"
    assert _extract_domain("bad-email") is None
    assert _extract_domain(None) is None


@pytest.mark.asyncio
async def test_contact_enrichment_guess_company():
    """_guess_company maps known domains to company names."""
    from app.services.contact_enrichment import _guess_company
    assert _guess_company("google.com") == "Google"
    # Unknown domains get capitalized as a best guess
    result = _guess_company("unknowndomain12345.com")
    assert result is not None  # returns capitalized domain name as fallback


@pytest.mark.asyncio
async def test_contact_enrichment_auto_lead_score():
    """_auto_lead_score produces a score between 0-100."""
    from app.services.contact_enrichment import _auto_lead_score

    class FakeContact:
        email = "test@google.com"
        phone = "+1234567890"
        company = "Google"
        relationship = "client"
        source = "website"

    score = _auto_lead_score(FakeContact())
    assert 0 <= score <= 100
    assert score > 0


@pytest.mark.asyncio
async def test_batch_enrich_endpoint(client: AsyncClient):
    """POST /contacts/enrich returns enrichment results."""
    r = await client.post("/api/v1/contacts/enrich")
    assert r.status_code == 200
    body = r.json()
    assert "enriched" in body


@pytest.mark.asyncio
async def test_contact_enrichment_on_create(client: AsyncClient, monkeypatch):
    """Creating a contact triggers fire-and-forget enrichment."""
    calls = []

    async def fake_enrich(contact_id, org_id):
        calls.append((contact_id, org_id))

    from app.services import contact_enrichment
    monkeypatch.setattr(contact_enrichment, "enrich_contact_background", fake_enrich)

    r = await client.post("/api/v1/contacts", json={"name": "Enrich Test", "email": "test@microsoft.com"})
    assert r.status_code == 201


# ── Goal-to-Project Linking ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_goal_projects_empty(client: AsyncClient):
    """GET /goals/{id}/projects returns empty list when no projects linked."""
    gr = await client.post("/api/v1/goals", json={"title": "Test Goal", "target_date": "2026-12-31"})
    assert gr.status_code == 201
    goal_id = gr.json()["id"]

    r = await client.get(f"/api/v1/goals/{goal_id}/projects")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_goal_projects_linked(client: AsyncClient):
    """GET /goals/{id}/projects returns linked projects."""
    gr = await client.post("/api/v1/goals", json={"title": "Linked Goal", "target_date": "2026-12-31"})
    assert gr.status_code == 201
    goal_id = gr.json()["id"]

    pr = await client.post("/api/v1/projects", json={"title": "Linked Project", "goal_id": goal_id})
    assert pr.status_code == 201

    r = await client.get(f"/api/v1/goals/{goal_id}/projects")
    assert r.status_code == 200
    projects = r.json()
    assert len(projects) == 1
    assert projects[0]["title"] == "Linked Project"


@pytest.mark.asyncio
async def test_goal_projects_404(client: AsyncClient):
    """GET /goals/9999/projects returns 404 for non-existent goal."""
    r = await client.get("/api/v1/goals/9999/projects")
    assert r.status_code == 404


# ── Contact Intelligence ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_intelligence_endpoint(client: AsyncClient):
    """GET /contacts/intelligence returns intelligence summary."""
    r = await client.get("/api/v1/contacts/intelligence")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)


@pytest.mark.asyncio
async def test_contact_rescore_endpoint(client: AsyncClient, monkeypatch):
    """POST /contacts/intelligence/rescore returns scoring result."""
    async def fake_score(db, organization_id):
        return {"scored": 0, "updated": 0}

    from app.services import contact_intelligence
    monkeypatch.setattr(contact_intelligence, "batch_score_contacts", fake_score)

    r = await client.post("/api/v1/contacts/intelligence/rescore")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_contact_duplicates_endpoint(client: AsyncClient):
    """GET /contacts/duplicates returns list."""
    r = await client.get("/api/v1/contacts/duplicates")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_contact_pipeline_analytics(client: AsyncClient):
    """GET /contacts/pipeline-analytics returns analytics dict."""
    r = await client.get("/api/v1/contacts/pipeline-analytics")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
