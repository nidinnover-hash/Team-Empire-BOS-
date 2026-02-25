# ── POST /api/v1/notes ───────────────────────────────────────────────────────

async def test_create_note_returns_201(client):
    response = await client.post(
        "/api/v1/notes",
        json={"content": "Remember to drink water"},
    )
    assert response.status_code == 201


async def test_create_note_returns_correct_fields(client):
    response = await client.post(
        "/api/v1/notes",
        json={"content": "Remember to drink water"},
    )
    body = response.json()
    assert body["content"] == "Remember to drink water"
    assert "id" in body
    assert "created_at" in body


async def test_create_note_missing_content_returns_422(client):
    response = await client.post("/api/v1/notes", json={})
    assert response.status_code == 422


# ── GET /api/v1/notes ────────────────────────────────────────────────────────

async def test_list_notes_empty(client):
    response = await client.get("/api/v1/notes")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_notes_returns_all(client):
    await client.post("/api/v1/notes", json={"content": "note one"})
    await client.post("/api/v1/notes", json={"content": "note two"})

    items = (await client.get("/api/v1/notes")).json()
    assert len(items) == 2


async def test_list_notes_newest_first(client):
    await client.post("/api/v1/notes", json={"content": "first note"})
    await client.post("/api/v1/notes", json={"content": "second note"})

    items = (await client.get("/api/v1/notes")).json()
    assert items[0]["content"] == "second note"
    assert items[1]["content"] == "first note"
