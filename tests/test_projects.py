# ── POST /api/v1/projects ────────────────────────────────────────────────────

async def test_create_project_returns_201(client):
    response = await client.post(
        "/api/v1/projects",
        json={"title": "Launch mobile app"},
    )
    assert response.status_code == 201


async def test_create_project_returns_correct_fields(client):
    response = await client.post(
        "/api/v1/projects",
        json={"title": "Backend refactor", "category": "business"},
    )
    body = response.json()
    assert body["title"] == "Backend refactor"
    assert body["category"] == "business"
    assert body["status"] == "active"
    assert body["description"] is None
    assert "id" in body
    assert "created_at" in body


async def test_create_project_with_due_date(client):
    response = await client.post(
        "/api/v1/projects",
        json={"title": "Q2 Roadmap", "due_date": "2026-06-30"},
    )
    assert response.json()["due_date"] == "2026-06-30"


async def test_create_project_missing_title_returns_422(client):
    response = await client.post("/api/v1/projects", json={})
    assert response.status_code == 422


# ── GET /api/v1/projects ─────────────────────────────────────────────────────

async def test_list_projects_empty(client):
    response = await client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_projects_returns_all(client):
    await client.post("/api/v1/projects", json={"title": "Project Alpha"})
    await client.post("/api/v1/projects", json={"title": "Project Beta"})
    items = (await client.get("/api/v1/projects")).json()
    assert len(items) == 2


# ── PATCH /api/v1/projects/{id}/status ───────────────────────────────────────

async def test_update_project_status_to_completed(client):
    project_id = (
        await client.post("/api/v1/projects", json={"title": "Ship v1"})
    ).json()["id"]

    response = await client.patch(
        f"/api/v1/projects/{project_id}/status",
        json={"status": "completed"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


async def test_update_project_status_to_paused(client):
    project_id = (
        await client.post("/api/v1/projects", json={"title": "Stalled feature"})
    ).json()["id"]

    response = await client.patch(
        f"/api/v1/projects/{project_id}/status",
        json={"status": "paused"},
    )
    assert response.json()["status"] == "paused"


async def test_update_project_status_not_found_returns_404(client):
    response = await client.patch(
        "/api/v1/projects/99999/status",
        json={"status": "archived"},
    )
    assert response.status_code == 404


async def test_update_project_status_missing_body_returns_422(client):
    project_id = (
        await client.post("/api/v1/projects", json={"title": "Temp"})
    ).json()["id"]
    response = await client.patch(f"/api/v1/projects/{project_id}/status", json={})
    assert response.status_code == 422
