"""Tests for Share Packets — cross-workspace knowledge transfer."""

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


async def _create_two_workspaces():
    session, agen = await _get_session()
    try:
        ws_a = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Sales Brain", slug="sales-brain",
        ))
        ws_b = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Ops Brain", slug="ops-brain",
        ))
        await session.commit()
        return ws_a.id, ws_b.id
    finally:
        await agen.aclose()


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def test_create_share_packet(client):
    ws_a, ws_b = await _create_two_workspaces()
    resp = await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "content_type": "memory",
            "title": "Sales insight",
            "payload": '{"key": "top_client", "value": "Acme Corp"}',
        },
        headers=_ceo_headers(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "proposed"
    assert body["source_workspace_id"] == ws_a
    assert body["target_workspace_id"] == ws_b
    assert body["proposed_by"] == 1


async def test_cannot_share_to_same_workspace(client):
    ws_a, _ = await _create_two_workspaces()
    resp = await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_a,
            "content_type": "insight",
            "title": "Self share",
            "payload": "nope",
        },
        headers=_ceo_headers(),
    )
    assert resp.status_code == 400


async def test_list_share_packets_empty(client):
    resp = await client.get("/api/v1/share-packets", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_share_packets_filtered_by_workspace(client):
    ws_a, ws_b = await _create_two_workspaces()
    h = _ceo_headers()
    await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "title": "Share 1",
            "payload": "data",
        },
        headers=h,
    )
    # Filter by source workspace
    resp = await client.get(f"/api/v1/share-packets?workspace_id={ws_a}", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_get_share_packet_by_id(client):
    ws_a, ws_b = await _create_two_workspaces()
    h = _ceo_headers()
    create_resp = await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "title": "Fetch me",
            "payload": "data",
        },
        headers=h,
    )
    pid = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/share-packets/{pid}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Fetch me"


async def test_get_share_packet_not_found(client):
    resp = await client.get("/api/v1/share-packets/99999", headers=_ceo_headers())
    assert resp.status_code == 404


# ── Decision flow ────────────────────────────────────────────────────────────

async def test_approve_share_packet(client):
    ws_a, ws_b = await _create_two_workspaces()
    h = _ceo_headers()
    create_resp = await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "title": "Approve me",
            "payload": "important data",
        },
        headers=h,
    )
    pid = create_resp.json()["id"]

    decide_resp = await client.post(
        f"/api/v1/share-packets/{pid}/decide",
        json={"status": "approved", "decision_note": "LGTM"},
        headers=h,
    )
    assert decide_resp.status_code == 200
    body = decide_resp.json()
    assert body["status"] == "approved"
    assert body["decided_by"] == 1
    assert body["decision_note"] == "LGTM"


async def test_reject_share_packet(client):
    ws_a, ws_b = await _create_two_workspaces()
    h = _ceo_headers()
    create_resp = await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "title": "Reject me",
            "payload": "bad data",
        },
        headers=h,
    )
    pid = create_resp.json()["id"]

    decide_resp = await client.post(
        f"/api/v1/share-packets/{pid}/decide",
        json={"status": "rejected"},
        headers=h,
    )
    assert decide_resp.status_code == 200
    assert decide_resp.json()["status"] == "rejected"


# ── Apply flow ───────────────────────────────────────────────────────────────

async def test_apply_memory_share_packet(client):
    """Applying an approved memory packet copies it into the target workspace."""
    ws_a, ws_b = await _create_two_workspaces()
    h = _ceo_headers()

    # Create and approve
    create_resp = await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "content_type": "memory",
            "title": "Client insight",
            "payload": '{"key": "top_client", "value": "Acme Corp", "category": "sales"}',
        },
        headers=h,
    )
    pid = create_resp.json()["id"]
    await client.post(
        f"/api/v1/share-packets/{pid}/decide",
        json={"status": "approved"},
        headers=h,
    )

    # Apply
    apply_resp = await client.post(f"/api/v1/share-packets/{pid}/apply", headers=h)
    assert apply_resp.status_code == 200
    assert apply_resp.json()["status"] == "applied"

    # Verify memory landed in target workspace
    mem_resp = await client.get(
        f"/api/v1/memory/profile?workspace_id={ws_b}", headers=h,
    )
    assert mem_resp.status_code == 200
    keys = [e["key"] for e in mem_resp.json()]
    assert "top_client" in keys


async def test_apply_unapproved_packet_fails(client):
    ws_a, ws_b = await _create_two_workspaces()
    h = _ceo_headers()
    create_resp = await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "title": "Not approved",
            "payload": "data",
        },
        headers=h,
    )
    pid = create_resp.json()["id"]
    resp = await client.post(f"/api/v1/share-packets/{pid}/apply", headers=h)
    assert resp.status_code == 404


# ── RBAC ─────────────────────────────────────────────────────────────────────

async def test_manager_can_list_but_not_create(client):
    # Managers can list
    resp = await client.get("/api/v1/share-packets", headers=_manager_headers())
    assert resp.status_code == 200

    # Managers cannot create
    ws_a, ws_b = await _create_two_workspaces()
    resp = await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "title": "Nope",
            "payload": "data",
        },
        headers=_manager_headers(),
    )
    assert resp.status_code == 403


async def test_filter_by_status(client):
    ws_a, ws_b = await _create_two_workspaces()
    h = _ceo_headers()

    # Create two packets
    r1 = await client.post(
        "/api/v1/share-packets",
        json={"source_workspace_id": ws_a, "target_workspace_id": ws_b, "title": "P1", "payload": "d1"},
        headers=h,
    )
    await client.post(
        "/api/v1/share-packets",
        json={"source_workspace_id": ws_a, "target_workspace_id": ws_b, "title": "P2", "payload": "d2"},
        headers=h,
    )

    # Approve only one
    await client.post(
        f"/api/v1/share-packets/{r1.json()['id']}/decide",
        json={"status": "approved"},
        headers=h,
    )

    # Filter by proposed
    proposed = await client.get("/api/v1/share-packets?status=proposed", headers=h)
    assert len(proposed.json()) == 1
    assert proposed.json()[0]["title"] == "P2"

    # Filter by approved
    approved = await client.get("/api/v1/share-packets?status=approved", headers=h)
    assert len(approved.json()) == 1
    assert approved.json()[0]["title"] == "P1"
