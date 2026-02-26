"""Tests for cron monitor + DB backup endpoints."""




# ── Backup endpoints ─────────────────────────────────────────────────────────


async def test_backup_create_endpoint(client):
    r = await client.post("/api/v1/control/backup")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body


async def test_backup_list_endpoint(client):
    r = await client.get("/api/v1/control/backup/list")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert isinstance(body["backups"], list)


# ── Cron health endpoint ─────────────────────────────────────────────────────


async def test_cron_health_no_runs(client):
    """Empty DB — all jobs show as never_run."""
    r = await client.get("/api/v1/control/cron/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "alerts" in body
    assert isinstance(body["jobs"], list)
    for job in body["jobs"]:
        assert job["last_run"] is None


async def test_cron_health_shape(client):
    """Verify response shape matches expected fields."""
    r = await client.get("/api/v1/control/cron/health")
    body = r.json()
    assert "checked_at" in body
    assert "alert_count" in body
    job = body["jobs"][0]
    assert "job_name" in job
    assert "status" in job
    assert "silent_minutes" in job
    assert "max_silence_minutes" in job
    assert "failure_streak" in job
