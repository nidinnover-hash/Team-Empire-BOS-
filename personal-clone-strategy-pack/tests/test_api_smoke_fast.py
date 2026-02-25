async def test_fast_smoke_health_and_session(client):
    health = await client.get("/health")
    assert health.status_code in {200, 503}
    assert isinstance(health.json(), dict)

    session = await client.get("/web/session")
    assert session.status_code == 200
    body = session.json()
    assert isinstance(body, dict)
    assert "logged_in" in body


async def test_fast_smoke_integrations_core_endpoints(client):
    endpoints = [
        ("GET", "/api/v1/integrations", None, {200}),
        ("GET", "/api/v1/integrations/setup-guide", None, {200}),
        ("GET", "/api/v1/integrations/ai/status", None, {200}),
        ("GET", "/api/v1/integrations/github/status", None, {200, 404}),
        ("GET", "/api/v1/integrations/clickup/status", None, {200, 404}),
        ("GET", "/api/v1/integrations/digitalocean/status", None, {200, 404}),
        ("GET", "/api/v1/integrations/slack/status", None, {200, 404}),
    ]
    for method, path, payload, allowed in endpoints:
        if method == "GET":
            response = await client.get(path)
        elif payload is None:
            response = await client.post(path)
        else:
            response = await client.post(path, json=payload)
        assert response.status_code in allowed, f"{path} returned {response.status_code}"
