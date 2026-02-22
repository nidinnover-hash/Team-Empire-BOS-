# ── POST /api/v1/goals ───────────────────────────────────────────────────────

async def test_create_goal_returns_201(client):
    response = await client.post(
        "/api/v1/goals",
        json={"title": "Reach $1M ARR"},
    )
    assert response.status_code == 201


async def test_create_goal_returns_correct_fields(client):
    response = await client.post(
        "/api/v1/goals",
        json={"title": "10x team output", "category": "business"},
    )
    body = response.json()
    assert body["title"] == "10x team output"
    assert body["category"] == "business"
    assert body["status"] == "active"
    assert body["progress"] == 0
    assert body["description"] is None
    assert "id" in body
    assert "created_at" in body


async def test_create_goal_with_target_date(client):
    response = await client.post(
        "/api/v1/goals",
        json={"title": "Launch v2", "target_date": "2026-12-31"},
    )
    assert response.json()["target_date"] == "2026-12-31"


async def test_create_goal_missing_title_returns_422(client):
    response = await client.post("/api/v1/goals", json={})
    assert response.status_code == 422


# ── GET /api/v1/goals ────────────────────────────────────────────────────────

async def test_list_goals_empty(client):
    response = await client.get("/api/v1/goals")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_goals_returns_all(client):
    await client.post("/api/v1/goals", json={"title": "Goal A"})
    await client.post("/api/v1/goals", json={"title": "Goal B"})
    items = (await client.get("/api/v1/goals")).json()
    assert len(items) == 2


# ── PATCH /api/v1/goals/{id}/progress ────────────────────────────────────────

async def test_update_goal_progress(client):
    goal_id = (
        await client.post("/api/v1/goals", json={"title": "Ship feature"})
    ).json()["id"]

    response = await client.patch(
        f"/api/v1/goals/{goal_id}/progress",
        json={"progress": 50},
    )
    assert response.status_code == 200
    assert response.json()["progress"] == 50


async def test_update_goal_progress_to_100_autocompletes(client):
    goal_id = (
        await client.post("/api/v1/goals", json={"title": "Finish onboarding"})
    ).json()["id"]

    response = await client.patch(
        f"/api/v1/goals/{goal_id}/progress",
        json={"progress": 100},
    )
    body = response.json()
    assert body["progress"] == 100
    assert body["status"] == "completed"


async def test_update_goal_progress_rejects_out_of_range(client):
    goal_id = (
        await client.post("/api/v1/goals", json={"title": "Some goal"})
    ).json()["id"]

    response = await client.patch(
        f"/api/v1/goals/{goal_id}/progress",
        json={"progress": 101},
    )
    assert response.status_code == 422


async def test_update_goal_progress_not_found_returns_404(client):
    response = await client.patch(
        "/api/v1/goals/99999/progress",
        json={"progress": 50},
    )
    assert response.status_code == 404


# ── PATCH /api/v1/goals/{id}/status ──────────────────────────────────────────

async def test_update_goal_status_to_paused(client):
    goal_id = (
        await client.post("/api/v1/goals", json={"title": "Paused goal"})
    ).json()["id"]

    response = await client.patch(
        f"/api/v1/goals/{goal_id}/status",
        json={"status": "paused"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "paused"


async def test_update_goal_status_not_found_returns_404(client):
    response = await client.patch(
        "/api/v1/goals/99999/status",
        json={"status": "abandoned"},
    )
    assert response.status_code == 404
