# ── POST /api/v1/tasks ───────────────────────────────────────────────────────

async def test_create_task_returns_201(client):
    response = await client.post(
        "/api/v1/tasks",
        json={"title": "Buy groceries"},
    )
    assert response.status_code == 201


async def test_create_task_returns_correct_fields(client):
    response = await client.post(
        "/api/v1/tasks",
        json={"title": "Buy groceries"},
    )
    body = response.json()
    assert body["title"] == "Buy groceries"
    assert body["description"] is None
    assert body["is_done"] is False
    assert body["completed_at"] is None
    assert "id" in body
    assert "created_at" in body


async def test_create_task_with_description(client):
    response = await client.post(
        "/api/v1/tasks",
        json={"title": "Exercise", "description": "30 min run"},
    )
    assert response.json()["description"] == "30 min run"


async def test_create_task_missing_title_returns_422(client):
    response = await client.post("/api/v1/tasks", json={})
    assert response.status_code == 422


# ── GET /api/v1/tasks ────────────────────────────────────────────────────────

async def test_list_tasks_empty(client):
    response = await client.get("/api/v1/tasks")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_tasks_returns_all(client):
    await client.post("/api/v1/tasks", json={"title": "Task A"})
    await client.post("/api/v1/tasks", json={"title": "Task B"})

    items = (await client.get("/api/v1/tasks")).json()
    assert len(items) == 2


# ── PATCH /api/v1/tasks/{id} ─────────────────────────────────────────────────

async def test_mark_task_done(client):
    task_id = (
        await client.post("/api/v1/tasks", json={"title": "Write tests"})
    ).json()["id"]

    response = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"is_done": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_done"] is True
    assert body["completed_at"] is not None   # timestamp was set


async def test_reopen_task_clears_completed_at(client):
    task_id = (
        await client.post("/api/v1/tasks", json={"title": "Deploy app"})
    ).json()["id"]

    # Mark done
    await client.patch(f"/api/v1/tasks/{task_id}", json={"is_done": True})

    # Reopen
    response = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"is_done": False},
    )
    body = response.json()
    assert body["is_done"] is False
    assert body["completed_at"] is None   # timestamp cleared


async def test_update_task_not_found_returns_404(client):
    response = await client.patch(
        "/api/v1/tasks/99999",
        json={"is_done": True},
    )
    assert response.status_code == 404


async def test_update_task_empty_body_is_noop(client):
    task_id = (
        await client.post("/api/v1/tasks", json={"title": "Some task"})
    ).json()["id"]

    response = await client.patch(f"/api/v1/tasks/{task_id}", json={})
    assert response.status_code == 200
    assert response.json()["title"] == "Some task"  # unchanged
