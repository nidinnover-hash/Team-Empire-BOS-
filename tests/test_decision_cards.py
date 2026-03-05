"""Tests for Decision Cards — workspace-level human-in-the-loop."""

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.schemas.workspace import WorkspaceCreate
from app.services.workspace import create_workspace


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


def _ceo_headers():
    token = create_access_token({
        "id": 1, "email": "ceo@org1.com", "role": "CEO",
        "org_id": 1, "token_version": 1,
    })
    return {"Authorization": f"Bearer {token}"}


def _manager_headers():
    token = create_access_token({
        "id": 3, "email": "manager@org1.com", "role": "MANAGER",
        "org_id": 1, "token_version": 1,
    })
    return {"Authorization": f"Bearer {token}"}


async def _create_workspace():
    session, agen = await _get_session()
    try:
        ws = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Decision WS", slug="decision-ws",
        ))
        await session.commit()
        return ws.id
    finally:
        await agen.aclose()


def _card_payload(ws_id: int, **overrides):
    base = {
        "workspace_id": ws_id,
        "title": "Hire a new developer",
        "context_summary": "Team is overloaded. 3 open positions. Budget approved.",
        "options": [
            {"label": "Hire senior", "description": "Higher cost, faster ramp", "risk_level": "low"},
            {"label": "Hire junior", "description": "Lower cost, needs mentoring", "risk_level": "medium"},
            {"label": "Outsource", "description": "Flexible, IP risk", "risk_level": "high"},
        ],
        "recommendation": "Hire senior",
        "category": "hr",
        "urgency": "high",
    }
    base.update(overrides)
    return base


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def test_create_decision_card(client):
    ws_id = await _create_workspace()
    resp = await client.post(
        "/api/v1/decision-cards",
        json=_card_payload(ws_id),
        headers=_ceo_headers(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["title"] == "Hire a new developer"
    assert body["urgency"] == "high"
    assert body["category"] == "hr"
    assert body["recommendation"] == "Hire senior"
    assert body["proposed_by"] == 1
    assert body["workspace_id"] == ws_id


async def test_list_decision_cards_empty(client):
    resp = await client.get("/api/v1/decision-cards", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_filtered_by_workspace(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()
    await client.post("/api/v1/decision-cards", json=_card_payload(ws_id), headers=h)

    resp = await client.get(f"/api/v1/decision-cards?workspace_id={ws_id}", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp2 = await client.get("/api/v1/decision-cards?workspace_id=99999", headers=h)
    assert resp2.json() == []


async def test_list_filtered_by_status(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()
    r = await client.post("/api/v1/decision-cards", json=_card_payload(ws_id), headers=h)
    card_id = r.json()["id"]

    # Decide the card
    await client.post(
        f"/api/v1/decision-cards/{card_id}/decide",
        json={"chosen_option": "Hire senior"},
        headers=h,
    )

    # Create another pending one
    await client.post(
        "/api/v1/decision-cards",
        json=_card_payload(ws_id, title="Second decision"),
        headers=h,
    )

    pending = await client.get("/api/v1/decision-cards?status=pending", headers=h)
    assert len(pending.json()) == 1
    assert pending.json()[0]["title"] == "Second decision"

    decided = await client.get("/api/v1/decision-cards?status=decided", headers=h)
    assert len(decided.json()) == 1
    assert decided.json()[0]["chosen_option"] == "Hire senior"


async def test_list_filtered_by_urgency(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()
    await client.post(
        "/api/v1/decision-cards",
        json=_card_payload(ws_id, urgency="critical"),
        headers=h,
    )
    await client.post(
        "/api/v1/decision-cards",
        json=_card_payload(ws_id, title="Low urgency", urgency="low"),
        headers=h,
    )

    critical = await client.get("/api/v1/decision-cards?urgency=critical", headers=h)
    assert len(critical.json()) == 1


async def test_get_decision_card_by_id(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()
    r = await client.post("/api/v1/decision-cards", json=_card_payload(ws_id), headers=h)
    card_id = r.json()["id"]

    resp = await client.get(f"/api/v1/decision-cards/{card_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Hire a new developer"


async def test_get_decision_card_not_found(client):
    resp = await client.get("/api/v1/decision-cards/99999", headers=_ceo_headers())
    assert resp.status_code == 404


# ── Decision flow ────────────────────────────────────────────────────────────

async def test_decide_card(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()
    r = await client.post("/api/v1/decision-cards", json=_card_payload(ws_id), headers=h)
    card_id = r.json()["id"]

    resp = await client.post(
        f"/api/v1/decision-cards/{card_id}/decide",
        json={"chosen_option": "Hire senior", "decision_rationale": "Best long-term ROI"},
        headers=h,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "decided"
    assert body["chosen_option"] == "Hire senior"
    assert body["decision_rationale"] == "Best long-term ROI"
    assert body["decided_by"] == 1
    assert body["decided_at"] is not None


async def test_decide_already_decided_returns_404(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()
    r = await client.post("/api/v1/decision-cards", json=_card_payload(ws_id), headers=h)
    card_id = r.json()["id"]

    await client.post(
        f"/api/v1/decision-cards/{card_id}/decide",
        json={"chosen_option": "Hire senior"},
        headers=h,
    )
    # Try deciding again
    resp = await client.post(
        f"/api/v1/decision-cards/{card_id}/decide",
        json={"chosen_option": "Outsource"},
        headers=h,
    )
    assert resp.status_code == 404


async def test_defer_card(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()
    r = await client.post("/api/v1/decision-cards", json=_card_payload(ws_id), headers=h)
    card_id = r.json()["id"]

    resp = await client.post(
        f"/api/v1/decision-cards/{card_id}/defer",
        json={"decision_rationale": "Need more data from finance"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deferred"


# ── Pending count ────────────────────────────────────────────────────────────

async def test_pending_count(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()

    # Start at 0
    resp = await client.get(f"/api/v1/decision-cards/pending-count?workspace_id={ws_id}", headers=h)
    assert resp.json()["pending_count"] == 0

    # Create 2 cards
    await client.post("/api/v1/decision-cards", json=_card_payload(ws_id), headers=h)
    r2 = await client.post(
        "/api/v1/decision-cards",
        json=_card_payload(ws_id, title="Second"),
        headers=h,
    )

    resp = await client.get(f"/api/v1/decision-cards/pending-count?workspace_id={ws_id}", headers=h)
    assert resp.json()["pending_count"] == 2

    # Decide one
    await client.post(
        f"/api/v1/decision-cards/{r2.json()['id']}/decide",
        json={"chosen_option": "Hire senior"},
        headers=h,
    )
    resp = await client.get(f"/api/v1/decision-cards/pending-count?workspace_id={ws_id}", headers=h)
    assert resp.json()["pending_count"] == 1


# ── RBAC ─────────────────────────────────────────────────────────────────────

async def test_manager_can_list_but_not_create(client):
    resp = await client.get("/api/v1/decision-cards", headers=_manager_headers())
    assert resp.status_code == 200

    ws_id = await _create_workspace()
    resp = await client.post(
        "/api/v1/decision-cards",
        json=_card_payload(ws_id),
        headers=_manager_headers(),
    )
    assert resp.status_code == 403


async def test_manager_cannot_decide(client):
    ws_id = await _create_workspace()
    h = _ceo_headers()
    r = await client.post("/api/v1/decision-cards", json=_card_payload(ws_id), headers=h)
    card_id = r.json()["id"]

    resp = await client.post(
        f"/api/v1/decision-cards/{card_id}/decide",
        json={"chosen_option": "Hire senior"},
        headers=_manager_headers(),
    )
    assert resp.status_code == 403
