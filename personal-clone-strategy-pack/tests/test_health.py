async def test_health_returns_200(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


async def test_health_status_is_ok(client):
    body = (await client.get("/api/v1/health")).json()
    assert body["status"] == "ok"


async def test_health_database_is_ok(client):
    body = (await client.get("/api/v1/health")).json()
    assert body["database"] == "ok"
