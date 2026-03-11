"""Tests for batch 15 features: products, contracts, competitors, email analytics,
territories, referrals, knowledge base."""
from __future__ import annotations

import pytest

from app.services import (
    competitor as comp_svc,
)
from app.services import (
    contract as cont_svc,
)
from app.services import (
    email_analytics as ea_svc,
)
from app.services import (
    knowledge_base as kb_svc,
)
from app.services import (
    product_catalog as prod_svc,
)
from app.services import (
    referral as ref_svc,
)
from app.services import (
    territory as terr_svc,
)


def _obj(**kw):
    class _O:
        pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


TS = "2026-03-10T00:00:00+00:00"


# ── Products ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_product(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Widget", sku="W-001",
                    description=None, category=None, unit_price=9.99,
                    currency="USD", is_active=True, created_at=TS, updated_at=TS)
    monkeypatch.setattr(prod_svc, "create_product", fake)
    r = await client.post("/api/v1/products", json={"name": "Widget", "sku": "W-001", "unit_price": 9.99})
    assert r.status_code == 201
    assert r.json()["name"] == "Widget"


@pytest.mark.asyncio
async def test_list_products(client, monkeypatch):
    async def fake(db, org_id, **kw): return []
    monkeypatch.setattr(prod_svc, "list_products", fake)
    r = await client.get("/api/v1/products")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_delete_product(client, monkeypatch):
    async def fake(db, pid, org_id): return True
    monkeypatch.setattr(prod_svc, "delete_product", fake)
    r = await client.delete("/api/v1/products/1")
    assert r.status_code == 204


# ── Contracts ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_contract(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, title="Annual SaaS", deal_id=None,
                    contact_id=None, status="draft", value=5000.0,
                    start_date=None, end_date=None, renewal_date=None,
                    auto_renew=False, notes=None, created_at=TS, updated_at=TS)
    monkeypatch.setattr(cont_svc, "create_contract", fake)
    r = await client.post("/api/v1/contracts", json={"title": "Annual SaaS", "value": 5000})
    assert r.status_code == 201
    assert r.json()["title"] == "Annual SaaS"


@pytest.mark.asyncio
async def test_contract_summary(client, monkeypatch):
    async def fake(db, org_id):
        return {"draft": {"count": 1, "total_value": 5000}}
    monkeypatch.setattr(cont_svc, "get_summary", fake)
    r = await client.get("/api/v1/contracts/summary")
    assert r.status_code == 200
    assert "draft" in r.json()


# ── Competitors ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_competitor(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Acme Corp", website=None,
                    strengths=None, weaknesses=None, notes=None,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(comp_svc, "create_competitor", fake)
    r = await client.post("/api/v1/competitors", json={"name": "Acme Corp"})
    assert r.status_code == 201
    assert r.json()["name"] == "Acme Corp"


@pytest.mark.asyncio
async def test_link_competitor_to_deal(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, deal_id=10, competitor_id=1,
                    threat_level="high", win_loss_reason=None, created_at=TS)
    monkeypatch.setattr(comp_svc, "link_to_deal", fake)
    r = await client.post("/api/v1/competitors/deal-link", json={"deal_id": 10, "competitor_id": 1, "threat_level": "high"})
    assert r.status_code == 201
    assert r.json()["threat_level"] == "high"


@pytest.mark.asyncio
async def test_win_loss_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"high": 3, "medium": 5}
    monkeypatch.setattr(comp_svc, "get_win_loss_stats", fake)
    r = await client.get("/api/v1/competitors/win-loss-stats")
    assert r.status_code == 200
    assert r.json()["high"] == 3


# ── Email Analytics ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_email_event(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, event_type="opened", email_id=5,
                    contact_id=None, link_url=None, user_agent=None, created_at=TS)
    monkeypatch.setattr(ea_svc, "record_event", fake)
    r = await client.post("/api/v1/email-analytics", json={"event_type": "opened", "email_id": 5})
    assert r.status_code == 201
    assert r.json()["event_type"] == "opened"


@pytest.mark.asyncio
async def test_email_overview(client, monkeypatch):
    async def fake(db, org_id):
        return {"sent": 100, "opened": 60}
    monkeypatch.setattr(ea_svc, "get_overview", fake)
    r = await client.get("/api/v1/email-analytics/overview")
    assert r.status_code == 200
    assert r.json()["sent"] == 100


# ── Territories ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_territory(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="West Coast", region="US-West",
                    industry=None, description=None, assigned_user_id=None,
                    contact_count=0, deal_count=0, created_at=TS, updated_at=TS)
    monkeypatch.setattr(terr_svc, "create_territory", fake)
    r = await client.post("/api/v1/territories", json={"name": "West Coast", "region": "US-West"})
    assert r.status_code == 201
    assert r.json()["name"] == "West Coast"


@pytest.mark.asyncio
async def test_list_territories(client, monkeypatch):
    async def fake(db, org_id, **kw): return []
    monkeypatch.setattr(terr_svc, "list_territories", fake)
    r = await client.get("/api/v1/territories")
    assert r.status_code == 200
    assert r.json() == []


# ── Referrals ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_referral_source(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Partner A", tracking_code="PTNR-A",
                    reward_type="flat", reward_value=50.0, total_referrals=0,
                    total_conversions=0, total_rewards_paid=0.0, notes=None, created_at=TS)
    monkeypatch.setattr(ref_svc, "create_source", fake)
    r = await client.post("/api/v1/referrals/sources", json={"name": "Partner A", "tracking_code": "PTNR-A", "reward_value": 50})
    assert r.status_code == 201
    assert r.json()["tracking_code"] == "PTNR-A"


@pytest.mark.asyncio
async def test_create_referral(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, source_id=1, contact_id=None,
                    deal_id=None, status="pending", reward_amount=0.0, created_at=TS)
    monkeypatch.setattr(ref_svc, "create_referral", fake)
    r = await client.post("/api/v1/referrals", json={"source_id": 1})
    assert r.status_code == 201
    assert r.json()["source_id"] == 1


@pytest.mark.asyncio
async def test_referral_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"total_referrals": 10, "total_conversions": 3, "total_rewards": 150.0, "conversion_rate": 30.0}
    monkeypatch.setattr(ref_svc, "get_stats", fake)
    r = await client.get("/api/v1/referrals/stats")
    assert r.status_code == 200
    assert r.json()["total_referrals"] == 10


@pytest.mark.asyncio
async def test_convert_referral(client, monkeypatch):
    async def fake(db, rid, org_id, reward_amount=0.0):
        return _obj(id=1, organization_id=1, source_id=1, contact_id=None,
                    deal_id=None, status="converted", reward_amount=50.0, created_at=TS)
    monkeypatch.setattr(ref_svc, "convert_referral", fake)
    r = await client.post("/api/v1/referrals/1/convert", json={"reward_amount": 50})
    assert r.status_code == 200
    assert r.json()["status"] == "converted"


# ── Knowledge Base ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_article(client, monkeypatch):
    async def fake(db, *, organization_id, created_by_user_id, **kw):
        return _obj(id=1, organization_id=1, title="Getting Started", slug="getting-started",
                    content="Welcome!", category=None, tags_json="[]",
                    is_published=False, view_count=0, helpful_count=0,
                    created_by_user_id=1, created_at=TS, updated_at=TS)
    monkeypatch.setattr(kb_svc, "create_article", fake)
    r = await client.post("/api/v1/knowledge-base", json={"title": "Getting Started", "content": "Welcome!"})
    assert r.status_code == 201
    assert r.json()["slug"] == "getting-started"


@pytest.mark.asyncio
async def test_search_articles(client, monkeypatch):
    async def fake(db, org_id, query): return []
    monkeypatch.setattr(kb_svc, "search_articles", fake)
    r = await client.get("/api/v1/knowledge-base/search?q=help")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_record_view(client, monkeypatch):
    async def fake(db, aid, org_id):
        return _obj(id=1, organization_id=1, title="FAQ", slug="faq",
                    content="Answers", category=None, tags_json="[]",
                    is_published=True, view_count=5, helpful_count=2,
                    created_by_user_id=1, created_at=TS, updated_at=TS)
    monkeypatch.setattr(kb_svc, "record_view", fake)
    r = await client.post("/api/v1/knowledge-base/1/view")
    assert r.status_code == 200
    assert r.json()["view_count"] == 5
