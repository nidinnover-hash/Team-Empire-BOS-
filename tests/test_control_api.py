from app.core.security import create_access_token


def _auth_headers(user_id: int, email: str, role: str, org_id: int) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def test_control_compliance_run_and_report(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    run = await client.post("/api/v1/control/compliance/run", headers=headers)
    assert run.status_code == 200
    assert run.json()["mode"] == "suggest_only"

    report = await client.get("/api/v1/control/compliance/report", headers=headers)
    assert report.status_code == 200
    assert "violations" in report.json()


async def test_control_message_draft(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    resp = await client.post(
        "/api/v1/control/message-draft",
        json={"to": "mano", "topic": "Access cleanup", "violations": [{"title": "X", "severity": "HIGH"}]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body
    assert body["checklist"]

