# ── POST /api/v1/contacts ────────────────────────────────────────────────────

async def test_create_contact_returns_201(client):
    response = await client.post(
        "/api/v1/contacts",
        json={"name": "Alice Nguyen"},
    )
    assert response.status_code == 201


async def test_create_contact_returns_correct_fields(client):
    response = await client.post(
        "/api/v1/contacts",
        json={"name": "Bob Chen", "email": "bob@example.com", "company": "Acme"},
    )
    body = response.json()
    assert body["name"] == "Bob Chen"
    assert body["email"] == "bob@example.com"
    assert body["company"] == "Acme"
    assert body["relationship"] == "personal"
    assert "id" in body
    assert "created_at" in body


async def test_create_contact_with_business_relationship(client):
    response = await client.post(
        "/api/v1/contacts",
        json={"name": "Carol Kim", "relationship": "business", "role": "CTO"},
    )
    body = response.json()
    assert body["relationship"] == "business"
    assert body["role"] == "CTO"


async def test_create_contact_missing_name_returns_422(client):
    response = await client.post("/api/v1/contacts", json={"email": "no-name@example.com"})
    assert response.status_code == 422


# ── GET /api/v1/contacts ─────────────────────────────────────────────────────

async def test_list_contacts_empty(client):
    response = await client.get("/api/v1/contacts")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_contacts_returns_all(client):
    await client.post("/api/v1/contacts", json={"name": "Dave Lee"})
    await client.post("/api/v1/contacts", json={"name": "Eva Park"})

    items = (await client.get("/api/v1/contacts")).json()
    assert len(items) == 2


async def test_list_contacts_contains_created_entry(client):
    await client.post(
        "/api/v1/contacts",
        json={"name": "Frank Wu", "company": "DevCorp"},
    )
    items = (await client.get("/api/v1/contacts")).json()
    names = [c["name"] for c in items]
    assert "Frank Wu" in names


async def test_contact_optional_fields_default_none(client):
    response = await client.post("/api/v1/contacts", json={"name": "Grace Ho"})
    body = response.json()
    assert body["email"] is None
    assert body["phone"] is None
    assert body["notes"] is None
