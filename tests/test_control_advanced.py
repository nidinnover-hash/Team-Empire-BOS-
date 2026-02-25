from app.core.security import create_access_token


def _auth_headers(user_id: int = 1, email: str = "ceo@org1.com", role: str = "CEO", org_id: int = 1) -> dict[str, str]:
    token = create_access_token({"id": user_id, "email": email, "role": role, "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


async def test_control_advanced_endpoints(client):
    headers = _auth_headers()

    run = await client.post("/api/v1/control/execute-plan", json={"challenge": "Resolve complex tech blockers"}, headers=headers)
    assert run.status_code == 200
    payload = run.json()
    assert payload["ok"] is True
    assert "data_quality" in payload

    dq = await client.get("/api/v1/control/data-quality", headers=headers)
    assert dq.status_code == 200
    assert "missing_identity_count" in dq.json()

    sla = await client.get("/api/v1/control/sla/manager", headers=headers)
    assert sla.status_code == 200
    assert "status" in sla.json()

    sim = await client.post(
        "/api/v1/control/scenario/simulate",
        json={"challenge": "Complex release stabilization", "blockers_count": 5, "top_n": 3},
        headers=headers,
    )
    assert sim.status_code == 200
    assert "projected_risk_drop_percent" in sim.json()

    packet = await client.get("/api/v1/control/weekly-board-packet", headers=headers)
    assert packet.status_code == 200
    assert "top_actions" in packet.json()

    cockpit = await client.get("/api/v1/control/cockpit/multi-org", headers=headers)
    assert cockpit.status_code == 200
    assert "organizations" in cockpit.json()

    playbook = await client.get("/api/v1/control/founder-playbook/today", headers=headers)
    assert playbook.status_code == 200
    pb = playbook.json()
    assert pb["core_values"] == ["Love", "Growth", "Strategic Execution"]
    assert "today_focus" in pb

    posture = await client.get("/api/v1/control/security/posture", headers=headers)
    assert posture.status_code == 200
    ps = posture.json()
    assert "status" in ps
    assert "open_issues" in ps

    morning = await client.get("/api/v1/control/ceo/morning-brief", headers=headers)
    assert morning.status_code == 200
    mb = morning.json()
    assert mb["mode"] == "suggest_only"
    assert "priority_actions" in mb

    brain = await client.post(
        "/api/v1/control/brain/train-data-driven",
        json={"challenge": "Train CEO brain with strict data evidence", "weeks": 1},
        headers=headers,
    )
    assert brain.status_code == 200
    bb = brain.json()
    assert bb["mode"] == "suggest_only"
    assert "data_collection" in bb
    assert "ceo_brain" in bb

    limits = await client.post(
        "/api/v1/control/brain/limitations-claude",
        json={"challenge": "Figure out clone limits and self-improve"},
        headers=headers,
    )
    assert limits.status_code == 200
    lb = limits.json()
    assert lb["mode"] == "suggest_only"
    assert "limitations" in lb
    assert "development_plan" in lb
