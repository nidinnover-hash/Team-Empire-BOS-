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
        json={"type": "gmail", "config_json": {"access_token": "token-demo"}},
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


async def test_control_integrations_health_endpoint(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    resp = await client.get("/api/v1/control/integrations/health", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "stale_count" in body
    assert "failing_count" in body
    if body["items"]:
        assert body["items"][0]["state"] in {"healthy", "degraded", "stale", "down"}
        assert "suggested_actions" in body["items"][0]


async def test_control_system_health_endpoint(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    resp = await client.get("/api/v1/control/system-health", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] in {"ok", "degraded", "down"}
    assert isinstance(body["dependencies"], list)
    assert "integrations" in body


async def test_control_storage_metrics_endpoint(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    resp = await client.get("/api/v1/control/storage/metrics", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "generated_at" in body
    assert "memory_context_cache" in body
    for key in ("hits", "misses", "stale_pruned", "evictions", "size"):
        assert key in body["memory_context_cache"]
    assert "ai_router_recent_calls_1h" in body
    assert "ai_router_fallback_rate_1h" in body
    assert "ai_router_errors_1h" in body
    assert "ai_router_provider_counts_1h" in body
    assert "approval_feedback_stats" in body


async def test_control_scheduler_jobs_endpoints(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    replay = await client.post(
        "/api/v1/control/jobs/replay",
        json={"job_name": "compliance_run"},
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json()["job_name"] == "compliance_run"

    listing = await client.get("/api/v1/control/jobs/runs", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert "items" in body
    if body["items"]:
        assert "failure_streak" in body["items"][0]
        assert "dead_letter_candidate" in body["items"][0]


async def test_control_ceo_morning_brief(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    resp = await client.get("/api/v1/control/ceo/morning-brief", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "suggest_only"
    assert "priority_actions" in body
    assert "risk_snapshot" in body


async def test_control_self_learning_train_endpoint(client):
    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    resp = await client.post("/api/v1/control/brain/self-learning-train", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "week_start_date" in body
    assert "learning_signals_30d" in body

    second = await client.post("/api/v1/control/brain/self-learning-train", headers=headers)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["ok"] is True
    assert second_body.get("skipped") is True
