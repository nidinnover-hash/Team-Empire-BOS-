from tests.conftest import _make_auth_headers


async def test_intelligence_summary_returns_kpis(client):
    headers = _make_auth_headers(1, "ceo@org1.com", "CEO")
    response = await client.get("/api/v1/intelligence/summary?window_days=7", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["organization_id"] == 1
    assert "decision_summary" in payload
    assert "kpis" in payload
    assert 0.0 <= payload["confidence_score"] <= 1.0
    assert payload["risk_tier"] in {"low", "medium", "high"}
    assert isinstance(payload["reasoning"], list)
    assert payload["reasoning"]


async def test_intelligence_diff_returns_expected_shape(client):
    headers = _make_auth_headers(1, "ceo@org1.com", "CEO")
    response = await client.get("/api/v1/intelligence/diff", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["organization_id"] == 1
    assert isinstance(payload["changes"], list)
    assert payload["changes"]
    assert "what_changed_since_yesterday" in payload
    assert "risk_increased" in payload
    assert "opportunity_increased" in payload
    assert "urgent_decision" in payload
    assert 0.0 <= payload["confidence_score"] <= 1.0
    assert payload["risk_tier"] in {"low", "medium", "high"}
    assert isinstance(payload["reasoning"], list)


async def test_daily_run_writes_decision_trace(client):
    headers = _make_auth_headers(1, "ceo@org1.com", "CEO")
    team_member = await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Maya",
            "role_title": "Operations",
            "team": "ops",
            "skills": "Execution",
            "ai_level": 2,
            "current_project": "Daily run",
        },
        headers=headers,
    )
    assert team_member.status_code == 201

    run = await client.post("/api/v1/ops/daily-run?draft_email_limit=0", headers=headers)
    assert run.status_code == 200
    run_payload = run.json()
    assert "decision_trace_id" in run_payload
    assert "confidence_score" in run_payload
    assert run_payload["risk_tier"] in {"low", "medium", "high"}
    assert isinstance(run_payload["confidence_reasoning"], list)
    assert run_payload["confidence_reasoning"]

    traces = await client.get("/api/v1/intelligence/traces?limit=10", headers=headers)
    assert traces.status_code == 200
    rows = traces.json()
    found = next((item for item in rows if item["id"] == run_payload["decision_trace_id"]), None)
    assert found is not None
    assert found["risk_tier"] in {"low", "medium", "high"}
    assert isinstance(found["reasoning"], list)
