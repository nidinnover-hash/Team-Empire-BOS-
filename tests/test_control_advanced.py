from app.core.security import create_access_token


def _auth_headers(user_id: int = 1, email: str = "ceo@org1.com", role: str = "CEO", org_id: int = 1) -> dict[str, str]:
    token = create_access_token({"id": user_id, "email": email, "role": role, "org_id": org_id})
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
