"""Tests for Workspace CRUD, membership, and default workspace creation."""

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app


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


def _staff_headers():
    token = create_access_token({
        "id": 4, "email": "staff@org1.com", "role": "STAFF",
        "org_id": 1, "token_version": 1,
    })
    return {"Authorization": f"Bearer {token}"}


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def test_create_workspace(client):
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Sales Brain", "slug": "sales-brain", "workspace_type": "department"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Sales Brain"
    assert body["slug"] == "sales-brain"
    assert body["workspace_type"] == "department"
    assert body["is_default"] is False
    assert body["is_active"] is True


async def test_list_workspaces_empty(client):
    resp = await client.get("/api/v1/workspaces", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_workspaces_returns_created(client):
    await client.post(
        "/api/v1/workspaces",
        json={"name": "WS1", "slug": "ws1"},
        headers=_ceo_headers(),
    )
    await client.post(
        "/api/v1/workspaces",
        json={"name": "WS2", "slug": "ws2"},
        headers=_ceo_headers(),
    )
    resp = await client.get("/api/v1/workspaces", headers=_ceo_headers())
    assert resp.status_code == 200
    names = [w["name"] for w in resp.json()]
    assert "WS1" in names
    assert "WS2" in names


async def test_get_workspace_by_id(client):
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Ops Brain", "slug": "ops-brain"},
        headers=_ceo_headers(),
    )
    ws_id = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/workspaces/{ws_id}", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json()["slug"] == "ops-brain"


async def test_get_workspace_not_found(client):
    resp = await client.get("/api/v1/workspaces/99999", headers=_ceo_headers())
    assert resp.status_code == 404


async def test_update_workspace(client):
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Old Name", "slug": "old-name"},
        headers=_ceo_headers(),
    )
    ws_id = create_resp.json()["id"]
    resp = await client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": "New Name", "workspace_type": "project"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["workspace_type"] == "project"


async def test_update_workspace_not_found(client):
    resp = await client.patch(
        "/api/v1/workspaces/99999",
        json={"name": "X"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 404


async def test_deactivate_workspace(client):
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Temp", "slug": "temp"},
        headers=_ceo_headers(),
    )
    ws_id = create_resp.json()["id"]
    resp = await client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"is_active": False},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # No longer in active list
    list_resp = await client.get("/api/v1/workspaces", headers=_ceo_headers())
    ids = [w["id"] for w in list_resp.json()]
    assert ws_id not in ids


async def test_staff_cannot_create_workspace(client):
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Nope", "slug": "nope"},
        headers=_staff_headers(),
    )
    assert resp.status_code == 403


# ── Membership ───────────────────────────────────────────────────────────────

async def test_add_and_list_members(client):
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Team WS", "slug": "team-ws"},
        headers=_ceo_headers(),
    )
    ws_id = create_resp.json()["id"]

    # Add user 3 (manager)
    add_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"user_id": 3},
        headers=_ceo_headers(),
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["user_id"] == 3

    # List members
    list_resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/members",
        headers=_ceo_headers(),
    )
    assert list_resp.status_code == 200
    user_ids = [m["user_id"] for m in list_resp.json()]
    assert 3 in user_ids


async def test_add_member_with_role_override(client):
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "RO WS", "slug": "ro-ws"},
        headers=_ceo_headers(),
    )
    ws_id = create_resp.json()["id"]

    add_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"user_id": 3, "role_override": "ADMIN"},
        headers=_ceo_headers(),
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["role_override"] == "ADMIN"


async def test_remove_member(client):
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Del WS", "slug": "del-ws"},
        headers=_ceo_headers(),
    )
    ws_id = create_resp.json()["id"]

    await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"user_id": 3},
        headers=_ceo_headers(),
    )
    del_resp = await client.delete(
        f"/api/v1/workspaces/{ws_id}/members/3",
        headers=_ceo_headers(),
    )
    assert del_resp.status_code == 204

    # Should be empty
    list_resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/members",
        headers=_ceo_headers(),
    )
    assert list_resp.json() == []


async def test_remove_nonexistent_member(client):
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "RNM WS", "slug": "rnm-ws"},
        headers=_ceo_headers(),
    )
    ws_id = create_resp.json()["id"]
    resp = await client.delete(
        f"/api/v1/workspaces/{ws_id}/members/999",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 404


# ── Default workspace service ────────────────────────────────────────────────

async def test_ensure_default_workspace_creates_one(client):
    from app.services.workspace import ensure_default_workspace

    session, agen = await _get_session()
    try:
        ws = await ensure_default_workspace(session, org_id=1)
        assert ws.name == "Default"
        assert ws.slug == "default"
        assert ws.is_default is True
        await session.commit()
    finally:
        await agen.aclose()


async def test_ensure_default_workspace_idempotent(client):
    from app.services.workspace import ensure_default_workspace

    session, agen = await _get_session()
    try:
        ws1 = await ensure_default_workspace(session, org_id=1)
        await session.commit()
    finally:
        await agen.aclose()

    session2, agen2 = await _get_session()
    try:
        ws2 = await ensure_default_workspace(session2, org_id=1)
        assert ws2.id == ws1.id
    finally:
        await agen2.aclose()


# ── Memory tables have workspace_id column ───────────────────────────────────

async def test_memory_models_have_workspace_id(client):
    """Verify workspace_id FK exists on all memory models."""
    from app.models.clone_memory import CloneMemoryEntry
    from app.models.memory import AvatarMemory, DailyContext, ProfileMemory
    from app.models.task import Task

    for model in (ProfileMemory, DailyContext, AvatarMemory, CloneMemoryEntry, Task):
        assert hasattr(model, "workspace_id"), f"{model.__name__} missing workspace_id"
        col = model.__table__.columns["workspace_id"]
        assert col.nullable is True, f"{model.__name__}.workspace_id should be nullable"
