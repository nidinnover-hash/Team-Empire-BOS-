"""Tests for /api/v1/export endpoint."""


async def test_export_returns_structure(client):
    resp = await client.get("/api/v1/export")
    assert resp.status_code == 200
    body = resp.json()
    assert "exported_at" in body
    assert "organization_id" in body
    for key in ("tasks", "projects", "goals", "notes", "contacts", "commands"):
        assert key in body
        assert isinstance(body[key], list)


async def test_export_includes_created_task(client):
    # Create a task first
    await client.post("/api/v1/tasks", json={"title": "Export test task"})

    resp = await client.get("/api/v1/export")
    assert resp.status_code == 200
    body = resp.json()
    titles = [t["title"] for t in body["tasks"]]
    assert "Export test task" in titles
