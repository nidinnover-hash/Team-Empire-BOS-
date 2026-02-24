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


async def test_control_health_summary_counts(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)

    # one open task
    task_resp = await client.post("/api/v1/tasks", json={"title": "Health summary task"}, headers=headers)
    assert task_resp.status_code == 201

    # one pending approval
    approval_resp = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "send_message", "payload_json": {}},
        headers=headers,
    )
    assert approval_resp.status_code == 201

    # one connected integration
    integration_resp = await client.post(
        "/api/v1/integrations/connect",
        json={"type": "slack", "config_json": {"access_token": "xoxb-demo-token"}},
        headers=headers,
    )
    assert integration_resp.status_code == 201

    summary = await client.get("/api/v1/control/health-summary", headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["open_tasks"] >= 1
    assert body["pending_approvals"] >= 1
    assert body["connected_integrations"] >= 1
    assert body["failing_integrations"] >= 0
    assert "generated_at" in body


async def test_control_ceo_status_contains_risk_buckets(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    resp = await client.get("/api/v1/control/ceo/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "infra_risks" in body
    assert "cost_alerts" in body
    assert body["mode"] == "suggest_only"


async def test_control_github_identity_map_upsert_and_list(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    upsert = await client.post(
        "/api/v1/control/github-identity-map/upsert",
        json={"company_email": "sharon@empireoe.com", "github_login": "sharonempire"},
        headers=headers,
    )
    assert upsert.status_code == 200
    assert upsert.json()["ok"] is True

    listing = await client.get("/api/v1/control/github-identity-map", headers=headers)
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["count"] >= 1
    assert any(item["company_email"] == "sharon@empireoe.com" for item in payload["items"])
