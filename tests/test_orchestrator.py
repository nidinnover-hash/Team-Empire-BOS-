"""Tests for CEO Orchestrator — cross-workspace intelligence."""

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


def _staff_headers():
    token = create_access_token({
        "id": 4, "email": "staff@org1.com", "role": "STAFF",
        "org_id": 1, "token_version": 1,
    })
    return {"Authorization": f"Bearer {token}"}


async def _setup_workspaces():
    """Create two workspaces for testing."""
    session, agen = await _get_session()
    try:
        ws_a = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Sales", slug="sales",
        ))
        ws_b = await create_workspace(session, org_id=1, data=WorkspaceCreate(
            name="Operations", slug="operations",
        ))
        await session.commit()
        return ws_a.id, ws_b.id
    finally:
        await agen.aclose()


# ── Briefing ─────────────────────────────────────────────────────────────────

async def test_briefing_empty_org(client):
    """Briefing with no workspaces returns zero counts."""
    resp = await client.get("/api/v1/orchestrator/briefing", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_workspaces"] == 0
    assert body["workspace_health"] == []
    assert body["patterns"] == []
    assert body["total_pending_decisions"] == 0
    assert body["total_pending_shares"] == 0


async def test_briefing_with_workspaces(client):
    """Briefing returns health for each workspace."""
    ws_a, ws_b = await _setup_workspaces()
    resp = await client.get("/api/v1/orchestrator/briefing", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_workspaces"] == 2
    assert body["active_workspaces"] == 2
    assert len(body["workspace_health"]) == 2
    names = [h["workspace_name"] for h in body["workspace_health"]]
    assert "Sales" in names
    assert "Operations" in names


async def test_briefing_shows_pending_decisions(client):
    """Pending decisions aggregate in briefing."""
    ws_a, ws_b = await _setup_workspaces()
    h = _ceo_headers()

    # Create decision cards
    for i in range(3):
        await client.post(
            "/api/v1/decision-cards",
            json={
                "workspace_id": ws_a,
                "title": f"Decision {i}",
                "context_summary": "Context",
                "options": [
                    {"label": "A", "description": "Option A"},
                    {"label": "B", "description": "Option B"},
                ],
            },
            headers=h,
        )

    resp = await client.get("/api/v1/orchestrator/briefing", headers=h)
    body = resp.json()
    assert body["total_pending_decisions"] == 3

    # Sales workspace health should reflect pending decisions
    sales = next(wh for wh in body["workspace_health"] if wh["workspace_name"] == "Sales")
    assert sales["pending_decisions"] == 3


async def test_briefing_shows_pending_shares(client):
    ws_a, ws_b = await _setup_workspaces()
    h = _ceo_headers()

    await client.post(
        "/api/v1/share-packets",
        json={
            "source_workspace_id": ws_a,
            "target_workspace_id": ws_b,
            "title": "Insight",
            "payload": "data",
        },
        headers=h,
    )

    resp = await client.get("/api/v1/orchestrator/briefing", headers=h)
    assert resp.json()["total_pending_shares"] == 1


async def test_briefing_detects_isolated_workspace(client):
    """Workspaces with no share packets trigger 'gap' pattern."""
    ws_a, ws_b = await _setup_workspaces()
    resp = await client.get("/api/v1/orchestrator/briefing", headers=_ceo_headers())
    body = resp.json()

    gap_patterns = [p for p in body["patterns"] if p["pattern_type"] == "gap"]
    # Both workspaces are isolated (no shares)
    assert len(gap_patterns) == 2


async def test_briefing_detects_decision_bottleneck(client):
    """Workspace with 3+ pending decisions triggers 'opportunity' pattern."""
    ws_a, ws_b = await _setup_workspaces()
    h = _ceo_headers()

    for i in range(4):
        await client.post(
            "/api/v1/decision-cards",
            json={
                "workspace_id": ws_a,
                "title": f"D{i}",
                "context_summary": "C",
                "options": [{"label": "X"}, {"label": "Y"}],
            },
            headers=h,
        )

    resp = await client.get("/api/v1/orchestrator/briefing", headers=h)
    opp_patterns = [p for p in resp.json()["patterns"] if p["pattern_type"] == "opportunity"]
    assert len(opp_patterns) >= 1
    assert "bottleneck" in opp_patterns[0]["title"].lower()


# ── Workspace Health ─────────────────────────────────────────────────────────

async def test_workspace_health_endpoint(client):
    ws_a, _ = await _setup_workspaces()
    resp = await client.get(
        f"/api/v1/orchestrator/workspace-health/{ws_a}",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == ws_a
    assert "health_score" in body
    assert body["status"] in ["healthy", "attention", "critical"]


async def test_workspace_health_not_found(client):
    resp = await client.get(
        "/api/v1/orchestrator/workspace-health/99999",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 404


async def test_workspace_health_with_memory(client):
    """Memory entries boost health score."""
    ws_a, _ = await _setup_workspaces()
    h = _ceo_headers()

    # Add profile memory
    for i in range(5):
        await client.post(
            f"/api/v1/memory/profile?workspace_id={ws_a}",
            json={"key": f"fact_{i}", "value": f"val_{i}", "category": "identity"},
            headers=h,
        )

    resp = await client.get(f"/api/v1/orchestrator/workspace-health/{ws_a}", headers=h)
    body = resp.json()
    assert body["memory_count"] == 5
    assert body["health_score"] > 0


# ── RBAC ─────────────────────────────────────────────────────────────────────

async def test_staff_cannot_access_briefing(client):
    resp = await client.get("/api/v1/orchestrator/briefing", headers=_staff_headers())
    assert resp.status_code == 403


async def test_manager_can_access_workspace_health(client):
    ws_a, _ = await _setup_workspaces()
    resp = await client.get(
        f"/api/v1/orchestrator/workspace-health/{ws_a}",
        headers=_manager_headers(),
    )
    assert resp.status_code == 200


async def test_manager_cannot_access_briefing(client):
    resp = await client.get("/api/v1/orchestrator/briefing", headers=_manager_headers())
    assert resp.status_code == 403
