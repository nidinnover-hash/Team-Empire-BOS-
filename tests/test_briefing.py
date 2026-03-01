from datetime import date

from tests.conftest import _make_auth_headers


async def test_executive_briefing_returns_expected_sections(client):
    ceo_headers = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
    manager_headers = _make_auth_headers(3, "manager@org1.com", "MANAGER", 1)

    context_res = await client.post(
        "/api/v1/memory/context",
        json={
            "date": date.today().isoformat(),
            "context_type": "priority",
            "content": "Finalize release checklist",
            "related_to": "Phase 1",
        },
        headers=ceo_headers,
    )
    assert context_res.status_code == 201

    approval_res = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "assign_task", "payload_json": {"team": "tech"}},
        headers=manager_headers,
    )
    assert approval_res.status_code == 201

    response = await client.get("/api/v1/briefing/executive", headers=ceo_headers)
    assert response.status_code == 200
    data = response.json()

    assert "team_summary" in data
    assert "approvals" in data
    assert "inbox" in data
    assert "today_priorities" in data
    assert isinstance(data["today_priorities"], list)
    assert data["approvals"]["pending_count"] >= 1


async def test_executive_briefing_staff_forbidden(client):
    staff_headers = _make_auth_headers(4, "staff@org1.com", "STAFF", 1)
    response = await client.get("/api/v1/briefing/executive", headers=staff_headers)
    assert response.status_code == 403
