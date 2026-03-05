"""Tests for workspace-scoped memory isolation (Phase 2)."""

from datetime import date

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.schemas.workspace import WorkspaceCreate
from app.services.clone_memory import retrieve_similar, store_memory
from app.services.memory import _memory_context_cache, invalidate_memory_cache
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


# ── Workspace-scoped profile memory ─────────────────────────────────────────

async def test_profile_memory_scoped_to_workspace(client):
    """Profile memory in workspace A is invisible from workspace B."""

    session, agen = await _get_session()
    try:
        ws_a = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Brain A", slug="brain-a",
        ))
        ws_b = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Brain B", slug="brain-b",
        ))
        await session.commit()
    finally:
        await agen.aclose()

    h = _ceo_headers()

    # Create profile entry in workspace A
    resp_a = await client.post(
        f"/api/v1/memory/profile?workspace_id={ws_a.id}",
        json={"key": "owner_name", "value": "Alice", "category": "identity"},
        headers=h,
    )
    assert resp_a.status_code == 201

    # Create same key in workspace B with different value
    resp_b = await client.post(
        f"/api/v1/memory/profile?workspace_id={ws_b.id}",
        json={"key": "owner_name", "value": "Bob", "category": "identity"},
        headers=h,
    )
    assert resp_b.status_code == 201

    # List workspace A — should only see Alice
    list_a = await client.get(
        f"/api/v1/memory/profile?workspace_id={ws_a.id}", headers=h,
    )
    assert list_a.status_code == 200
    vals_a = [e["value"] for e in list_a.json()]
    assert "Alice" in vals_a
    assert "Bob" not in vals_a

    # List workspace B — should only see Bob
    list_b = await client.get(
        f"/api/v1/memory/profile?workspace_id={ws_b.id}", headers=h,
    )
    assert list_b.status_code == 200
    vals_b = [e["value"] for e in list_b.json()]
    assert "Bob" in vals_b
    assert "Alice" not in vals_b


async def test_profile_memory_no_workspace_returns_all(client):
    """Without workspace_id, profile memory returns all entries for the org."""
    h = _ceo_headers()

    # Create entries without workspace scope
    await client.post(
        "/api/v1/memory/profile",
        json={"key": "global_key", "value": "global_val", "category": "identity"},
        headers=h,
    )

    resp = await client.get("/api/v1/memory/profile", headers=h)
    assert resp.status_code == 200
    keys = [e["key"] for e in resp.json()]
    assert "global_key" in keys


# ── Workspace-scoped daily context ───────────────────────────────────────────

async def test_daily_context_scoped_to_workspace(client):
    """Daily context entries are isolated per workspace."""

    session, agen = await _get_session()
    try:
        ws = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Context WS", slug="ctx-ws",
        ))
        await session.commit()
    finally:
        await agen.aclose()

    h = _ceo_headers()

    # Add context to workspace
    resp = await client.post(
        f"/api/v1/memory/context?workspace_id={ws.id}",
        json={"context_type": "priority", "content": "WS priority", "date": str(date.today())},
        headers=h,
    )
    assert resp.status_code == 201

    # Add context without workspace
    await client.post(
        "/api/v1/memory/context",
        json={"context_type": "priority", "content": "Org priority", "date": str(date.today())},
        headers=h,
    )

    # List with workspace filter — only WS entry
    scoped = await client.get(
        f"/api/v1/memory/context?workspace_id={ws.id}", headers=h,
    )
    assert scoped.status_code == 200
    contents = [e["content"] for e in scoped.json()]
    assert "WS priority" in contents
    assert "Org priority" not in contents


# ── Service-level clone memory isolation ─────────────────────────────────────

async def test_clone_memory_store_and_retrieve_with_workspace(client):
    """Clone memory stored in a workspace is only retrievable within it."""

    session, agen = await _get_session()
    try:
        ws = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Clone WS", slug="clone-ws",
        ))
        await session.commit()

        # Store memory in workspace
        await store_memory(
            session, org_id=1, employee_id=1,
            situation="client asked about pricing",
            action_taken="sent proposal",
            outcome="positive",
            workspace_id=ws.id,
        )

        # Store memory without workspace
        await store_memory(
            session, org_id=1, employee_id=1,
            situation="client asked about pricing globally",
            action_taken="sent global proposal",
            outcome="positive",
        )

        # Retrieve scoped to workspace
        ws_results = await retrieve_similar(
            session, org_id=1, employee_id=1,
            situation_query="pricing",
            workspace_id=ws.id,
        )
        assert len(ws_results) == 1
        assert "proposal" in ws_results[0].action_taken

        # Retrieve without workspace — gets all
        all_results = await retrieve_similar(
            session, org_id=1, employee_id=1,
            situation_query="pricing",
        )
        assert len(all_results) == 2
    finally:
        await agen.aclose()


# ── Memory cache key includes workspace_id ───────────────────────────────────

async def test_memory_cache_uses_workspace_key(client):
    """Verify cache invalidation is workspace-aware."""

    # Manually populate cache with different workspace keys
    _memory_context_cache[(1, None)] = (999999999.0, "org-level")
    _memory_context_cache[(1, 10)] = (999999999.0, "ws-10")
    _memory_context_cache[(1, 20)] = (999999999.0, "ws-20")

    # Invalidate specific workspace
    invalidate_memory_cache(1, workspace_id=10)
    assert (1, 10) not in _memory_context_cache
    assert (1, None) in _memory_context_cache
    assert (1, 20) in _memory_context_cache

    # Invalidate all for org
    invalidate_memory_cache(1)
    assert (1, None) not in _memory_context_cache
    assert (1, 20) not in _memory_context_cache
