from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute

from app.core.config import settings
from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.product_bundle import BundleItem
from app.services import feature_flags
from app.services import organization as organization_service
from app.services import product_bundle as product_bundle_service
from app.services import quote as quote_service
from app.services import sales_playbook as playbook_service
from app.services import survey as survey_service
from tests.conftest import _make_auth_headers


def _obj(**kwargs):
    class Obj:
        pass

    out = Obj()
    for key, value in kwargs.items():
        setattr(out, key, value)
    return out


@pytest.fixture(autouse=True)
def _enable_crm_flags(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_QUOTES", True)
    monkeypatch.setattr(settings, "FEATURE_PLAYBOOKS", True)
    monkeypatch.setattr(settings, "FEATURE_SURVEYS", True)


async def _get_client_db_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


@pytest.mark.asyncio
async def test_quote_service_tenant_scope_on_list_get_update_delete(db):
    quote = await quote_service.create_quote(db, organization_id=1, title="Scoped")

    org2_list = await quote_service.list_quotes(db, organization_id=2)
    org2_get = await quote_service.get_quote(db, quote.id, organization_id=2)
    org2_update = await quote_service.update_quote(db, quote.id, organization_id=2, title="Nope")
    org2_delete = await quote_service.delete_quote(db, quote.id, organization_id=2)

    assert org2_list == []
    assert org2_get is None
    assert org2_update is None
    assert org2_delete is False


@pytest.mark.asyncio
async def test_playbook_service_tenant_scope_on_list_get_update_delete(db):
    playbook = await playbook_service.create_playbook(db, organization_id=1, name="Scoped")

    org2_list = await playbook_service.list_playbooks(db, organization_id=2)
    org2_get = await playbook_service.get_playbook(db, playbook.id, organization_id=2)
    org2_update = await playbook_service.update_playbook(db, playbook.id, organization_id=2, name="Nope")
    org2_delete = await playbook_service.delete_playbook(db, playbook.id, organization_id=2)

    assert org2_list == []
    assert org2_get is None
    assert org2_update is None
    assert org2_delete is False


@pytest.mark.asyncio
async def test_survey_service_tenant_scope_on_list_get_update_delete(db):
    survey = await survey_service.create_survey(db, organization_id=1, title="Scoped")

    org2_list = await survey_service.list_surveys(db, organization_id=2)
    org2_get = await survey_service.get_survey(db, survey.id, organization_id=2)
    org2_update = await survey_service.update_survey(db, survey.id, organization_id=2, title="Nope")
    org2_delete = await survey_service.delete_survey(db, survey.id, organization_id=2)

    assert org2_list == []
    assert org2_get is None
    assert org2_update is None
    assert org2_delete is False


@pytest.mark.asyncio
async def test_cross_tenant_quote_access_denied_at_api(client):
    created = await client.post("/api/v1/quotes", json={"title": "Tenant Locked"})
    assert created.status_code == 201
    quote_id = created.json()["id"]

    org2_headers = _make_auth_headers(user_id=2, email="ceo@org2.com", role="CEO", org_id=2)
    assert (await client.get(f"/api/v1/quotes/{quote_id}", headers=org2_headers)).status_code == 404
    assert (
        await client.put(
            f"/api/v1/quotes/{quote_id}",
            json={"title": "cross-tenant"},
            headers=org2_headers,
        )
    ).status_code == 404
    assert (await client.delete(f"/api/v1/quotes/{quote_id}", headers=org2_headers)).status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_product_bundle_items_not_exposed(client):
    session, agen = await _get_client_db_session()
    try:
        bundle = await product_bundle_service.create_bundle(
            session,
            organization_id=1,
            name="Private",
            bundle_price=100,
        )
        session.add(BundleItem(bundle_id=bundle.id, product_id=1, quantity=2, unit_price=50))
        await session.commit()
    finally:
        await agen.aclose()

    org2_headers = _make_auth_headers(user_id=2, email="ceo@org2.com", role="CEO", org_id=2)
    response = await client.get(f"/api/v1/product-bundles/{bundle.id}/items", headers=org2_headers)

    # Accept either strict 404 or empty collection; never expose foreign-tenant items.
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        assert response.json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload", "svc_attr", "event_name"),
    [
        ("/api/v1/quotes", {"title": "Q-1"}, "create_quote", "quote_created"),
        ("/api/v1/playbooks", {"name": "P-1"}, "create_playbook", "playbook_created"),
        ("/api/v1/surveys", {"title": "S-1"}, "create_survey", "survey_created"),
    ],
)
async def test_create_mutations_emit_audit_events(client, monkeypatch, path, payload, svc_attr, event_name):
    now = datetime.now(UTC)
    events: list[str] = []

    async def fake_record_action(_db, **kwargs):
        events.append(kwargs["event_type"])
        return _obj(id=1)

    if path == "/api/v1/quotes":
        from app.api.v1.endpoints import quotes as endpoint

        async def fake_create(_db, *, organization_id, created_by_user_id, **kwargs):
            return _obj(
                id=11,
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

        monkeypatch.setattr(quote_service, svc_attr, fake_create)
        monkeypatch.setattr(endpoint, "record_action", fake_record_action)
    elif path == "/api/v1/playbooks":
        from app.api.v1.endpoints import playbooks as endpoint

        async def fake_create(_db, *, organization_id, **kwargs):
            return _obj(
                id=21,
                organization_id=organization_id,
                name=kwargs["name"],
                deal_stage=None,
                description=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            )

        monkeypatch.setattr(playbook_service, svc_attr, fake_create)
        monkeypatch.setattr(endpoint, "record_action", fake_record_action)
    else:
        from app.api.v1.endpoints import surveys as endpoint

        async def fake_create(_db, *, organization_id, **kwargs):
            return _obj(
                id=31,
                organization_id=organization_id,
                title=kwargs["title"],
                description=None,
                is_active=True,
                total_responses=0,
                created_at=now,
                updated_at=now,
            )

        monkeypatch.setattr(survey_service, svc_attr, fake_create)
        monkeypatch.setattr(endpoint, "record_action", fake_record_action)

    response = await client.post(path, json=payload)
    assert response.status_code == 201
    assert events == [event_name]


def test_route_map_parity_for_hardened_surfaces():
    route_map: dict[tuple[str, str], str] = {}
    for route in fastapi_app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"}):
            route_map[(route.path, method)] = route.name

    expected = {
        ("/api/v1/quotes", "GET"),
        ("/api/v1/quotes", "POST"),
        ("/api/v1/quotes/{quote_id}", "PUT"),
        ("/api/v1/playbooks", "GET"),
        ("/api/v1/playbooks", "POST"),
        ("/api/v1/surveys", "GET"),
        ("/api/v1/surveys", "POST"),
        ("/api/v1/approvals/request", "POST"),
        ("/api/v1/approvals/{approval_id}/approve", "POST"),
        ("/api/v1/product-bundles/{bundle_id}/items", "GET"),
    }
    missing = [f"{method} {path}" for (path, method) in sorted(expected) if (path, method) not in route_map]
    assert not missing, "Missing hardened routes:\n" + "\n".join(missing)


@pytest.mark.asyncio
async def test_effective_feature_flag_fallback_to_global_default(db, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_QUOTES", True)

    async def fake_get_feature_flags(_db, _org_id):
        return 1, {}

    monkeypatch.setattr(organization_service, "get_feature_flags", fake_get_feature_flags)
    enabled = await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=1,
        flag_name="quotes",
    )
    assert enabled is True


@pytest.mark.asyncio
async def test_approval_request_denies_cross_tenant_payload(client):
    response = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 2, "approval_type": "task_execution", "payload_json": {"task": "x"}},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_manager_cannot_approve_pending_approval(client):
    create = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "task_execution", "payload_json": {"task": "x"}},
    )
    assert create.status_code == 201
    approval_id = create.json()["id"]

    manager_headers = _make_auth_headers(user_id=3, email="manager@org1.com", role="MANAGER", org_id=1)
    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "ok"},
        headers=manager_headers,
    )
    assert approve.status_code == 403


@pytest.mark.asyncio
async def test_approval_request_idempotency_prevents_duplicate_rows(client):
    payload = {"organization_id": 1, "approval_type": "task_execution", "payload_json": {"task": "x"}}
    first = await client.post("/api/v1/approvals/request", json=payload, headers={"Idempotency-Key": "safe-idem-1"})
    second = await client.post("/api/v1/approvals/request", json=payload, headers={"Idempotency-Key": "safe-idem-1"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.asyncio
async def test_forecast_rollup_upsert_is_idempotent_per_natural_key(db):
    from app.services import forecast_rollup as forecast_rollup_service

    payload = {
        "period": "2026-Q1",
        "period_type": "quarterly",
        "group_by": "team",
        "group_value": "Sales",
        "committed": 100,
        "best_case": 120,
        "pipeline": 150,
        "weighted_pipeline": 110,
        "closed_won": 70,
        "target": 200,
        "attainment_pct": 35,
    }
    first = await forecast_rollup_service.upsert_rollup(db, organization_id=1, **payload)
    second = await forecast_rollup_service.upsert_rollup(
        db,
        organization_id=1,
        **{**payload, "committed": 130, "attainment_pct": 40},
    )
    rows = await forecast_rollup_service.list_rollups(db, org_id=1, period="2026-Q1", group_by="team")

    assert second.id == first.id
    assert len([r for r in rows if r.group_value == "Sales"]) == 1


@pytest.mark.asyncio
async def test_quote_update_endpoint_ignores_protected_fields(client):
    created = await client.post("/api/v1/quotes", json={"title": "Protected"})
    assert created.status_code == 201
    quote_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/quotes/{quote_id}",
        json={
            "title": "Changed",
            "organization_id": 2,
            "created_by_user_id": 99,
            "id": 999,
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "Changed"
    assert body["organization_id"] == 1
    assert body["created_by_user_id"] == 1
    assert body["id"] == quote_id


@pytest.mark.asyncio
async def test_survey_submit_response_updates_counter(db):
    survey = await survey_service.create_survey(db, organization_id=1, title="Counter")
    assert survey.total_responses == 0

    await survey_service.submit_response(
        db,
        organization_id=1,
        survey_id=survey.id,
        score=9,
        nps_score=9,
        feedback="great",
    )
    refreshed = await survey_service.get_survey(db, survey.id, organization_id=1)
    assert refreshed is not None
    assert refreshed.total_responses == 1


@pytest.mark.asyncio
async def test_approval_list_query_bounds_enforced(client):
    low_limit = await client.get("/api/v1/approvals?limit=0")
    high_limit = await client.get("/api/v1/approvals?limit=501")
    high_offset = await client.get("/api/v1/approvals?offset=10001")

    assert low_limit.status_code == 422
    assert high_limit.status_code == 422
    assert high_offset.status_code == 422
