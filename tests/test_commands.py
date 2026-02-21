# ── POST /api/v1/commands ────────────────────────────────────────────────────

async def test_create_command_returns_201(client):
    response = await client.post(
        "/api/v1/commands",
        json={"command_text": "What is 2 + 2?"},
    )
    assert response.status_code == 201


async def test_create_command_returns_correct_fields(client):
    response = await client.post(
        "/api/v1/commands",
        json={"command_text": "Hello clone"},
    )
    body = response.json()
    assert body["command_text"] == "Hello clone"
    assert body["ai_response"] is None   # no AI call yet in v1
    assert "id" in body
    assert "created_at" in body


async def test_create_command_with_ai_response(client):
    response = await client.post(
        "/api/v1/commands",
        json={
            "command_text": "Summarise my day",
            "ai_response": "You had 3 meetings and shipped a feature.",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ai_response"] == "You had 3 meetings and shipped a feature."


async def test_create_command_missing_command_text_returns_422(client):
    # command_text is required — sending empty body must fail validation
    response = await client.post("/api/v1/commands", json={})
    assert response.status_code == 422


# ── GET /api/v1/commands ─────────────────────────────────────────────────────

async def test_list_commands_empty(client):
    response = await client.get("/api/v1/commands")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_commands_returns_all(client):
    await client.post("/api/v1/commands", json={"command_text": "first"})
    await client.post("/api/v1/commands", json={"command_text": "second"})

    items = (await client.get("/api/v1/commands")).json()
    assert len(items) == 2


async def test_list_commands_newest_first(client):
    await client.post("/api/v1/commands", json={"command_text": "oldest"})
    await client.post("/api/v1/commands", json={"command_text": "middle"})
    await client.post("/api/v1/commands", json={"command_text": "newest"})

    items = (await client.get("/api/v1/commands")).json()
    assert items[0]["command_text"] == "newest"
    assert items[-1]["command_text"] == "oldest"
