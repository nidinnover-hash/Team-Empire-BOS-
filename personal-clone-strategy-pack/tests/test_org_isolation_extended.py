from __future__ import annotations

from datetime import datetime, timezone

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.decision_trace import DecisionTrace
from app.models.event import Event


def _auth_headers(user_id: int, email: str, role: str, org_id: int) -> dict[str, str]:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def _create_second_org(client, headers: dict[str, str]) -> int:
    response = await client.post(
        "/api/v1/orgs",
        json={"name": "Org Two", "slug": "org-two"},
        headers=headers,
    )
    assert response.status_code == 201
    return int(response.json()["id"])


async def _seed_cross_org_rows() -> None:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        session.add_all(
            [
                DecisionTrace(
                    organization_id=1,
                    trace_type="daily_run",
                    title="Org1 trace",
                    summary="Org1 only",
                    confidence_score=0.8,
                ),
                DecisionTrace(
                    organization_id=2,
                    trace_type="daily_run",
                    title="Org2 trace",
                    summary="Org2 only",
                    confidence_score=0.8,
                ),
                Event(
                    organization_id=1,
                    event_type="org1_event",
                    actor_user_id=1,
                    entity_type="integration",
                    entity_id=1,
                    payload_json={"org": 1},
                    created_at=datetime.now(timezone.utc),
                ),
                Event(
                    organization_id=2,
                    event_type="org2_event",
                    actor_user_id=2,
                    entity_type="integration",
                    entity_id=2,
                    payload_json={"org": 2},
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.commit()
    finally:
        await agen.aclose()


async def test_cross_org_intelligence_traces_are_isolated(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)
    await _seed_cross_org_rows()

    resp_org1 = await client.get("/api/v1/intelligence/traces", headers=ceo_org1)
    assert resp_org1.status_code == 200
    titles_org1 = {item["title"] for item in resp_org1.json()}
    assert "Org1 trace" in titles_org1
    assert "Org2 trace" not in titles_org1

    ceo_org2 = _auth_headers(2, "ceo@org2.com", "CEO", 2)
    resp_org2 = await client.get("/api/v1/intelligence/traces", headers=ceo_org2)
    assert resp_org2.status_code == 200
    titles_org2 = {item["title"] for item in resp_org2.json()}
    assert "Org2 trace" in titles_org2
    assert "Org1 trace" not in titles_org2


async def test_cross_org_ops_events_are_isolated(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)
    await _seed_cross_org_rows()

    resp_org1 = await client.get("/api/v1/ops/events", headers=ceo_org1)
    assert resp_org1.status_code == 200
    events_org1 = {item["event_type"] for item in resp_org1.json()}
    assert "org1_event" in events_org1
    assert "org2_event" not in events_org1

    ceo_org2 = _auth_headers(2, "ceo@org2.com", "CEO", 2)
    resp_org2 = await client.get("/api/v1/ops/events", headers=ceo_org2)
    assert resp_org2.status_code == 200
    events_org2 = {item["event_type"] for item in resp_org2.json()}
    assert "org2_event" in events_org2
    assert "org1_event" not in events_org2


async def test_cross_org_integration_list_is_isolated(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)

    create = await client.post(
        "/api/v1/integrations/connect",
        json={"type": "github", "config_json": {"access_token": "abc"}},
        headers=ceo_org1,
    )
    assert create.status_code == 201

    resp_org1 = await client.get("/api/v1/integrations", headers=ceo_org1)
    assert resp_org1.status_code == 200
    types_org1 = {item["type"] for item in resp_org1.json()}
    assert "github" in types_org1

    ceo_org2 = _auth_headers(2, "ceo@org2.com", "CEO", 2)
    resp_org2 = await client.get("/api/v1/integrations", headers=ceo_org2)
    assert resp_org2.status_code == 200
    types_org2 = {item["type"] for item in resp_org2.json()}
    assert "github" not in types_org2
