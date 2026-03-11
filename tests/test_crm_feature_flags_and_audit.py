from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.services import quote as quote_svc
from app.services import sales_playbook as playbook_svc
from app.services import survey as survey_svc
from tests.conftest import _make_auth_headers


def _obj(**kw):
    class _O:
        pass

    o = _O()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


@pytest.fixture(autouse=True)
def _enable_crm_flags(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_QUOTES", True)
    monkeypatch.setattr(settings, "FEATURE_PLAYBOOKS", True)
    monkeypatch.setattr(settings, "FEATURE_SURVEYS", True)


@pytest.mark.asyncio
async def test_quotes_create_records_audit_event(client, monkeypatch):
    from app.api.v1.endpoints import quotes as quotes_ep

    now = datetime.now(UTC)
    events: list[str] = []

    async def fake_create_quote(db, *, organization_id, created_by_user_id, **kwargs):
        return _obj(
            id=9,
            organization_id=organization_id,
            title=kwargs["title"],
            deal_id=None,
            contact_id=None,
            status="draft",
            subtotal=0,
            discount_percent=0,
            tax_percent=0,
            total=0,
            currency="USD",
            expiry_date=None,
            notes=None,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )

    async def fake_record_action(db, **kwargs):
        events.append(kwargs["event_type"])
        return _obj(id=1)

    monkeypatch.setattr(quote_svc, "create_quote", fake_create_quote)
    monkeypatch.setattr(quotes_ep, "record_action", fake_record_action)

    response = await client.post("/api/v1/quotes", json={"title": "Q-100"})
    assert response.status_code == 201
    assert events == ["quote_created"]


@pytest.mark.asyncio
async def test_quotes_create_denies_staff(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    response = await client.post("/api/v1/quotes", json={"title": "Q-denied"}, headers=staff_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_quotes_flag_disabled_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_QUOTES", False)
    response = await client.get("/api/v1/quotes")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_quotes_effective_flag_can_disable_when_global_true(client, monkeypatch):
    from app.api.v1.endpoints import quotes as quotes_ep

    async def _disabled(_db, _org_id):
        return False

    monkeypatch.setattr(quotes_ep, "quotes_enabled", _disabled)
    response = await client.get("/api/v1/quotes")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_playbooks_create_records_audit_event(client, monkeypatch):
    from app.api.v1.endpoints import playbooks as playbooks_ep

    now = datetime.now(UTC)
    events: list[str] = []

    async def fake_create_playbook(db, *, organization_id, **kwargs):
        return _obj(
            id=7,
            organization_id=organization_id,
            name=kwargs["name"],
            deal_stage=kwargs.get("deal_stage"),
            description=kwargs.get("description"),
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    async def fake_record_action(db, **kwargs):
        events.append(kwargs["event_type"])
        return _obj(id=2)

    monkeypatch.setattr(playbook_svc, "create_playbook", fake_create_playbook)
    monkeypatch.setattr(playbooks_ep, "record_action", fake_record_action)

    response = await client.post("/api/v1/playbooks", json={"name": "Discovery"})
    assert response.status_code == 201
    assert events == ["playbook_created"]


@pytest.mark.asyncio
async def test_playbooks_create_denies_staff(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    response = await client.post("/api/v1/playbooks", json={"name": "Denied"}, headers=staff_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_playbooks_flag_disabled_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_PLAYBOOKS", False)
    response = await client.get("/api/v1/playbooks")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_surveys_create_records_audit_event(client, monkeypatch):
    from app.api.v1.endpoints import surveys as surveys_ep

    now = datetime.now(UTC)
    events: list[str] = []

    async def fake_create_survey(db, *, organization_id, **kwargs):
        return _obj(
            id=5,
            organization_id=organization_id,
            title=kwargs["title"],
            description=None,
            is_active=True,
            total_responses=0,
            created_at=now,
            updated_at=now,
        )

    async def fake_record_action(db, **kwargs):
        events.append(kwargs["event_type"])
        return _obj(id=3)

    monkeypatch.setattr(survey_svc, "create_survey", fake_create_survey)
    monkeypatch.setattr(surveys_ep, "record_action", fake_record_action)

    response = await client.post("/api/v1/surveys", json={"title": "CSAT 2026"})
    assert response.status_code == 201
    assert events == ["survey_created"]


@pytest.mark.asyncio
async def test_surveys_create_denies_staff(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    response = await client.post("/api/v1/surveys", json={"title": "Denied"}, headers=staff_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_surveys_flag_disabled_returns_404(client, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_SURVEYS", False)
    response = await client.get("/api/v1/surveys")
    assert response.status_code == 404
