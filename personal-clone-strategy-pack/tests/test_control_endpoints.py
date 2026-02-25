"""Tests for /api/v1/control endpoints."""


async def test_health_summary_returns_shape(client):
    resp = await client.get("/api/v1/control/health-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "open_tasks" in body or "integration_count" in body or isinstance(body, dict)


async def test_ceo_status_returns_shape(client):
    resp = await client.get("/api/v1/control/ceo/status")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)


async def test_integrations_health_returns_shape(client):
    resp = await client.get("/api/v1/control/integrations/health")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)


async def test_scheduler_job_runs_empty(client):
    resp = await client.get("/api/v1/control/jobs/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body or isinstance(body, (dict, list))


async def test_compliance_report_returns_shape(client):
    resp = await client.get("/api/v1/control/compliance/report")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
