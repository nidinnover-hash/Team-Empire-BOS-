"""Tests for batch 14 features."""
import pytest

from app.services import (
    commission as comm_svc,
    contact_score_history as csh_svc,
    deal_collaborator as dc_svc,
    email_suppression as es_svc,
    form_builder as fb_svc,
    meeting_note as mn_svc,
    revenue_recognition as rr_svc,
)


def _obj(**kw):
    class _O: pass
    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


TS = "2026-03-10T00:00:00+00:00"


# ── Commissions ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_commission_rule(client, monkeypatch):
    async def fake(db, *, organization_id, name, rate_percent=10.0, deal_type=None, stage=None, min_deal_value=0, max_deal_value=None):
        return _obj(id=1, organization_id=1, name=name, deal_type=deal_type, stage=stage,
                     rate_percent=rate_percent, min_deal_value=min_deal_value,
                     max_deal_value=max_deal_value, is_active=True, created_at=TS)
    monkeypatch.setattr(comm_svc, "create_rule", fake)
    r = await client.post("/api/v1/commissions/rules", json={"name": "Standard", "rate_percent": 15.0})
    assert r.status_code == 201
    assert r.json()["rate_percent"] == 15.0


@pytest.mark.asyncio
async def test_list_commission_rules(client, monkeypatch):
    async def fake(db, org_id, *, is_active=None): return []
    monkeypatch.setattr(comm_svc, "list_rules", fake)
    r = await client.get("/api/v1/commissions/rules")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_calculate_payout(client, monkeypatch):
    async def fake(db, *, organization_id, rule_id, deal_id, user_id, deal_value, split_percent=100.0, notes=None):
        return _obj(id=1, organization_id=1, rule_id=rule_id, deal_id=deal_id,
                     user_id=user_id, deal_value=deal_value,
                     commission_amount=deal_value * 0.1 * (split_percent / 100),
                     split_percent=split_percent, status="pending", notes=notes, created_at=TS)
    monkeypatch.setattr(comm_svc, "calculate_payout", fake)
    r = await client.post("/api/v1/commissions/payouts", json={
        "rule_id": 1, "deal_id": 1, "user_id": 1, "deal_value": 10000,
    })
    assert r.status_code == 201
    assert r.json()["commission_amount"] == 1000.0


@pytest.mark.asyncio
async def test_commission_summary(client, monkeypatch):
    async def fake(db, org_id):
        return {"pending": {"count": 3, "total": 5000.0}, "paid": {"count": 1, "total": 2000.0}}
    monkeypatch.setattr(comm_svc, "get_summary", fake)
    r = await client.get("/api/v1/commissions/summary")
    assert r.status_code == 200
    assert "pending" in r.json()


# ── Contact Score History ────────────────────────────────────


@pytest.mark.asyncio
async def test_record_contact_score(client, monkeypatch):
    async def fake(db, *, organization_id, contact_id, score, previous_score=None, change_reason=None, source="manual", details_json=None):
        return _obj(id=1, organization_id=1, contact_id=contact_id, score=score,
                     previous_score=previous_score, change_reason=change_reason,
                     source=source, details_json=details_json, created_at=TS)
    monkeypatch.setattr(csh_svc, "record_score", fake)
    r = await client.post("/api/v1/contact-scores", json={"contact_id": 1, "score": 85, "change_reason": "Email opened"})
    assert r.status_code == 201
    assert r.json()["score"] == 85


@pytest.mark.asyncio
async def test_get_score_history(client, monkeypatch):
    async def fake(db, org_id, contact_id, *, limit=50): return []
    monkeypatch.setattr(csh_svc, "get_history", fake)
    r = await client.get("/api/v1/contact-scores/1")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_score_trend(client, monkeypatch):
    async def fake(db, org_id, contact_id, *, limit=30):
        return [{"score": 80, "previous": 70, "reason": "Engaged", "source": "rule", "date": TS}]
    monkeypatch.setattr(csh_svc, "get_trend", fake)
    r = await client.get("/api/v1/contact-scores/1/trend")
    assert r.status_code == 200
    assert r.json()[0]["score"] == 80


# ── Deal Collaborators ───────────────────────────────────────


@pytest.mark.asyncio
async def test_add_deal_collaborator(client, monkeypatch):
    async def fake(db, *, organization_id, deal_id, user_id, role="support", notes=None, added_by_user_id=None):
        return _obj(id=1, organization_id=1, deal_id=deal_id, user_id=user_id,
                     role=role, notes=notes, added_by_user_id=added_by_user_id, created_at=TS)
    monkeypatch.setattr(dc_svc, "add_collaborator", fake)
    r = await client.post("/api/v1/deal-collaborators", json={"deal_id": 1, "user_id": 2, "role": "reviewer"})
    assert r.status_code == 201
    assert r.json()["role"] == "reviewer"


@pytest.mark.asyncio
async def test_list_deal_collaborators(client, monkeypatch):
    async def fake(db, org_id, deal_id): return []
    monkeypatch.setattr(dc_svc, "list_collaborators", fake)
    r = await client.get("/api/v1/deal-collaborators/1")
    assert r.status_code == 200


# ── Email Suppressions ───────────────────────────────────────


@pytest.mark.asyncio
async def test_add_email_suppression(client, monkeypatch):
    async def fake(db, *, organization_id, email_or_domain, suppression_type, reason=None, source="manual"):
        return _obj(id=1, organization_id=1, email_or_domain=email_or_domain,
                     suppression_type=suppression_type, reason=reason, source=source,
                     bounce_count=0, details_json=None, created_at=TS)
    monkeypatch.setattr(es_svc, "add_suppression", fake)
    r = await client.post("/api/v1/email-suppressions", json={
        "email_or_domain": "spam@test.com", "suppression_type": "manual",
    })
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_check_suppressed(client, monkeypatch):
    async def fake(db, org_id, email): return True
    monkeypatch.setattr(es_svc, "check_suppressed", fake)
    r = await client.get("/api/v1/email-suppressions/check", params={"email": "spam@test.com"})
    assert r.status_code == 200
    assert r.json()["suppressed"] is True


@pytest.mark.asyncio
async def test_suppression_stats(client, monkeypatch):
    async def fake(db, org_id): return {"bounce": 5, "manual": 3}
    monkeypatch.setattr(es_svc, "get_stats", fake)
    r = await client.get("/api/v1/email-suppressions/stats")
    assert r.status_code == 200
    assert r.json()["bounce"] == 5


# ── Form Builder ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_form(client, monkeypatch):
    async def fake(db, *, organization_id, name, description=None, fields=None, redirect_url=None, confirmation_message=None, created_by_user_id=None):
        return _obj(id=1, organization_id=1, name=name, description=description,
                     fields_json="[]", redirect_url=redirect_url,
                     confirmation_message=confirmation_message, is_active=True,
                     total_submissions=0, created_by_user_id=created_by_user_id, created_at=TS)
    monkeypatch.setattr(fb_svc, "create_form", fake)
    r = await client.post("/api/v1/forms", json={"name": "Contact Us"})
    assert r.status_code == 201
    assert r.json()["name"] == "Contact Us"


@pytest.mark.asyncio
async def test_list_forms(client, monkeypatch):
    async def fake(db, org_id, *, is_active=None): return []
    monkeypatch.setattr(fb_svc, "list_forms", fake)
    r = await client.get("/api/v1/forms")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_submit_form(client, monkeypatch):
    async def fake_get(db, form_id, org_id):
        return _obj(id=1, organization_id=1, name="F", total_submissions=0)
    monkeypatch.setattr(fb_svc, "get_form", fake_get)

    async def fake_submit(db, *, form_id, organization_id, data, contact_id=None, source_ip=None):
        return _obj(id=1, form_id=form_id, organization_id=1,
                     data_json="{}", contact_id=contact_id, source_ip=source_ip, created_at=TS)
    monkeypatch.setattr(fb_svc, "submit_form", fake_submit)
    r = await client.post("/api/v1/forms/1/submit", json={"data": {"name": "Nidin"}})
    assert r.status_code == 201


# ── Meeting Notes ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_meeting_note(client, monkeypatch):
    async def fake(db, *, organization_id, title, summary=None, full_notes=None, action_items=None, attendees=None, contact_id=None, deal_id=None, meeting_date=None, created_by_user_id=None):
        return _obj(id=1, organization_id=1, title=title, summary=summary,
                     full_notes=full_notes, action_items_json="[]", attendees_json="[]",
                     contact_id=contact_id, deal_id=deal_id, meeting_date=None,
                     created_by_user_id=created_by_user_id, created_at=TS)
    monkeypatch.setattr(mn_svc, "create_note", fake)
    r = await client.post("/api/v1/meeting-notes", json={"title": "Q1 Review", "summary": "Good quarter"})
    assert r.status_code == 201
    assert r.json()["title"] == "Q1 Review"


@pytest.mark.asyncio
async def test_list_meeting_notes(client, monkeypatch):
    async def fake(db, org_id, *, contact_id=None, deal_id=None, limit=50): return []
    monkeypatch.setattr(mn_svc, "list_notes", fake)
    r = await client.get("/api/v1/meeting-notes")
    assert r.status_code == 200


# ── Revenue Recognition ──────────────────────────────────────


@pytest.mark.asyncio
async def test_create_revenue_entry(client, monkeypatch):
    async def fake(db, *, organization_id, period, total_amount, recognized_amount=0.0, deferred_amount=0.0, recognition_stage="contract", deal_id=None, notes=None):
        return _obj(id=1, organization_id=1, deal_id=deal_id, period=period,
                     total_amount=total_amount, recognized_amount=recognized_amount,
                     deferred_amount=deferred_amount, recognition_stage=recognition_stage,
                     notes=notes, created_at=TS, updated_at=TS)
    monkeypatch.setattr(rr_svc, "create_entry", fake)
    r = await client.post("/api/v1/revenue", json={
        "period": "2026-03", "total_amount": 50000, "recognized_amount": 20000, "deferred_amount": 30000,
    })
    assert r.status_code == 201
    assert r.json()["total_amount"] == 50000


@pytest.mark.asyncio
async def test_list_revenue_entries(client, monkeypatch):
    async def fake(db, org_id, *, period=None, deal_id=None, limit=50): return []
    monkeypatch.setattr(rr_svc, "list_entries", fake)
    r = await client.get("/api/v1/revenue")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_revenue_period_summary(client, monkeypatch):
    async def fake(db, org_id, period):
        return {"period": period, "total_amount": 50000, "recognized_amount": 20000, "deferred_amount": 30000, "entry_count": 3}
    monkeypatch.setattr(rr_svc, "get_period_summary", fake)
    r = await client.get("/api/v1/revenue/summary/2026-03")
    assert r.status_code == 200
    assert r.json()["total_amount"] == 50000
