"""Tests for batch 16: quotes, surveys, playbooks, import mappings,
deal rotations, webhook events, custom reports."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import (
    custom_report as cr_svc,
)
from app.services import (
    deal_rotation as dr_svc,
)
from app.services import (
    import_mapping as im_svc,
)
from app.services import (
    quote as quote_svc,
)
from app.services import (
    sales_playbook as pb_svc,
)
from app.services import (
    survey as survey_svc,
)
from app.services import (
    webhook_event as we_svc,
)


def _obj(**kw):
    class _O:
        pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


TS = "2026-03-10T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _enable_crm_flags():
    saved = (
        settings.FEATURE_QUOTES,
        settings.FEATURE_PLAYBOOKS,
        settings.FEATURE_SURVEYS,
    )
    object.__setattr__(settings, "FEATURE_QUOTES", True)
    object.__setattr__(settings, "FEATURE_PLAYBOOKS", True)
    object.__setattr__(settings, "FEATURE_SURVEYS", True)
    yield
    object.__setattr__(settings, "FEATURE_QUOTES", saved[0])
    object.__setattr__(settings, "FEATURE_PLAYBOOKS", saved[1])
    object.__setattr__(settings, "FEATURE_SURVEYS", saved[2])


# ── Quotes ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_quote(client, monkeypatch):
    async def fake(db, *, organization_id, created_by_user_id, **kw):
        return _obj(id=1, organization_id=1, title="Q-001", deal_id=None,
                    contact_id=None, status="draft", subtotal=0, discount_percent=0,
                    tax_percent=0, total=0, currency="USD", expiry_date=None,
                    notes=None, created_by_user_id=1, created_at=TS, updated_at=TS)
    monkeypatch.setattr(quote_svc, "create_quote", fake)
    r = await client.post("/api/v1/quotes", json={"title": "Q-001"})
    assert r.status_code == 201
    assert r.json()["title"] == "Q-001"


@pytest.mark.asyncio
async def test_add_line_item(client, monkeypatch):
    async def fake(db, *, organization_id, quote_id, **kw):
        return _obj(id=1, organization_id=1, quote_id=1, product_id=None,
                    description="Widget", quantity=2, unit_price=10,
                    discount_percent=0, line_total=20, created_at=TS)
    monkeypatch.setattr(quote_svc, "add_line_item", fake)
    r = await client.post("/api/v1/quotes/1/lines", json={"description": "Widget", "quantity": 2, "unit_price": 10})
    assert r.status_code == 201
    assert r.json()["line_total"] == 20


@pytest.mark.asyncio
async def test_list_quotes(client, monkeypatch):
    async def fake(db, org_id, **kw): return []
    monkeypatch.setattr(quote_svc, "list_quotes", fake)
    r = await client.get("/api/v1/quotes")
    assert r.status_code == 200


# ── Surveys ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_survey(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, title="CSAT Q1", description=None,
                    questions_json="[]", is_active=True, total_responses=0,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(survey_svc, "create_survey", fake)
    r = await client.post("/api/v1/surveys", json={"title": "CSAT Q1"})
    assert r.status_code == 201
    assert r.json()["title"] == "CSAT Q1"


@pytest.mark.asyncio
async def test_submit_response(client, monkeypatch):
    async def fake(db, *, organization_id, survey_id, **kw):
        return _obj(id=1, organization_id=1, survey_id=1, contact_id=None,
                    score=9, nps_score=9, answers_json="{}", feedback=None, created_at=TS)
    monkeypatch.setattr(survey_svc, "submit_response", fake)
    r = await client.post("/api/v1/surveys/1/responses", json={"score": 9, "nps_score": 9})
    assert r.status_code == 201
    assert r.json()["score"] == 9


@pytest.mark.asyncio
async def test_get_nps(client, monkeypatch):
    async def fake(db, org_id, survey_id):
        return {"promoters": 5, "passives": 3, "detractors": 2, "nps": 30.0, "total": 10}
    monkeypatch.setattr(survey_svc, "get_nps", fake)
    r = await client.get("/api/v1/surveys/1/nps")
    assert r.status_code == 200
    assert r.json()["nps"] == 30.0


# ── Playbooks ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_playbook(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Discovery", deal_stage="discovery",
                    description=None, is_active=True, created_at=TS, updated_at=TS)
    monkeypatch.setattr(pb_svc, "create_playbook", fake)
    r = await client.post("/api/v1/playbooks", json={"name": "Discovery", "deal_stage": "discovery"})
    assert r.status_code == 201
    assert r.json()["name"] == "Discovery"


@pytest.mark.asyncio
async def test_add_step(client, monkeypatch):
    async def fake(db, *, organization_id, playbook_id, **kw):
        return _obj(id=1, organization_id=1, playbook_id=1, step_order=1,
                    title="Intro call", content=None, is_required=True, created_at=TS)
    monkeypatch.setattr(pb_svc, "add_step", fake)
    r = await client.post("/api/v1/playbooks/1/steps", json={"title": "Intro call", "step_order": 1, "is_required": True})
    assert r.status_code == 201
    assert r.json()["is_required"] is True


# ── Import Mappings ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_mapping(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="CRM Export",
                    entity_type="contact", column_map_json="{}",
                    transformers_json="[]", created_at=TS, updated_at=TS)
    monkeypatch.setattr(im_svc, "create_mapping", fake)
    r = await client.post("/api/v1/import-mappings", json={"name": "CRM Export"})
    assert r.status_code == 201
    assert r.json()["name"] == "CRM Export"


@pytest.mark.asyncio
async def test_record_import(client, monkeypatch):
    async def fake(db, *, organization_id, started_by_user_id, **kw):
        return _obj(id=1, organization_id=1, mapping_id=None, file_name="contacts.csv",
                    entity_type="contact", total_rows=100, success_rows=95,
                    error_rows=5, status="completed", errors_json="[]",
                    started_by_user_id=1, created_at=TS, completed_at=None)
    monkeypatch.setattr(im_svc, "record_import", fake)
    r = await client.post("/api/v1/import-mappings/imports", json={"file_name": "contacts.csv", "total_rows": 100, "success_rows": 95, "error_rows": 5})
    assert r.status_code == 201
    assert r.json()["success_rows"] == 95


@pytest.mark.asyncio
async def test_import_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"total_imports": 5, "total_success_rows": 500, "total_error_rows": 10}
    monkeypatch.setattr(im_svc, "get_import_stats", fake)
    r = await client.get("/api/v1/import-mappings/imports/stats")
    assert r.status_code == 200
    assert r.json()["total_imports"] == 5


# ── Deal Rotations ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_queue(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, name="Sales Team", user_ids_json="[1,2,3]",
                    current_index=0, total_assignments=0, is_active=True,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(dr_svc, "create_queue", fake)
    r = await client.post("/api/v1/deal-rotations", json={"name": "Sales Team", "user_ids": [1, 2, 3]})
    assert r.status_code == 201
    assert r.json()["name"] == "Sales Team"


@pytest.mark.asyncio
async def test_assign_next(client, monkeypatch):
    async def fake(db, *, organization_id, queue_id, deal_id):
        return _obj(id=1, organization_id=1, queue_id=1, deal_id=10,
                    assigned_user_id=2, created_at=TS)
    monkeypatch.setattr(dr_svc, "assign_next", fake)
    r = await client.post("/api/v1/deal-rotations/1/assign", json={"deal_id": 10})
    assert r.status_code == 201
    assert r.json()["assigned_user_id"] == 2


@pytest.mark.asyncio
async def test_fairness(client, monkeypatch):
    async def fake(db, org_id, queue_id):
        return {"distribution": {"1": 5, "2": 4, "3": 5}, "total": 14}
    monkeypatch.setattr(dr_svc, "get_fairness", fake)
    r = await client.get("/api/v1/deal-rotations/1/fairness")
    assert r.status_code == 200
    assert r.json()["total"] == 14


# ── Webhook Events ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_event(client, monkeypatch):
    async def fake(db, *, organization_id, **kw):
        return _obj(id=1, organization_id=1, source="stripe", event_type="payment.completed",
                    payload_json="{}", headers_json="{}", status="received",
                    error_message=None, processed_at=None, created_at=TS)
    monkeypatch.setattr(we_svc, "capture_event", fake)
    r = await client.post("/api/v1/webhook-events", json={"source": "stripe", "event_type": "payment.completed"})
    assert r.status_code == 201
    assert r.json()["source"] == "stripe"


@pytest.mark.asyncio
async def test_replay_event(client, monkeypatch):
    async def fake(db, eid, org_id):
        return _obj(id=2, organization_id=1, source="stripe", event_type="payment.completed",
                    payload_json="{}", headers_json="{}", status="replayed",
                    error_message=None, processed_at=None, created_at=TS)
    monkeypatch.setattr(we_svc, "replay_event", fake)
    r = await client.post("/api/v1/webhook-events/1/replay")
    assert r.status_code == 201
    assert r.json()["status"] == "replayed"


@pytest.mark.asyncio
async def test_webhook_stats(client, monkeypatch):
    async def fake(db, org_id):
        return {"received": 50, "processed": 45, "failed": 5}
    monkeypatch.setattr(we_svc, "get_stats", fake)
    r = await client.get("/api/v1/webhook-events/stats")
    assert r.status_code == 200
    assert r.json()["processed"] == 45


# ── Custom Reports ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_report(client, monkeypatch):
    async def fake(db, *, organization_id, created_by_user_id, **kw):
        return _obj(id=1, organization_id=1, name="Pipeline Report", description=None,
                    entity_type="deal", filters_json="{}", grouping_json="[]",
                    aggregation_json="[]", columns_json="[]", is_shared=False,
                    created_by_user_id=1, run_count=0, last_run_at=None,
                    created_at=TS, updated_at=TS)
    monkeypatch.setattr(cr_svc, "create_report", fake)
    r = await client.post("/api/v1/custom-reports", json={"name": "Pipeline Report"})
    assert r.status_code == 201
    assert r.json()["name"] == "Pipeline Report"


@pytest.mark.asyncio
async def test_run_report(client, monkeypatch):
    async def fake(db, rid, org_id):
        return _obj(id=1, organization_id=1, name="Pipeline Report", description=None,
                    entity_type="deal", is_shared=False, created_by_user_id=1,
                    run_count=1, last_run_at=TS, created_at=TS, updated_at=TS)
    monkeypatch.setattr(cr_svc, "record_run", fake)
    r = await client.post("/api/v1/custom-reports/1/run")
    assert r.status_code == 200
    assert r.json()["run_count"] == 1


@pytest.mark.asyncio
async def test_list_reports(client, monkeypatch):
    async def fake(db, org_id, **kw): return []
    monkeypatch.setattr(cr_svc, "list_reports", fake)
    r = await client.get("/api/v1/custom-reports")
    assert r.status_code == 200
    assert r.json() == []
