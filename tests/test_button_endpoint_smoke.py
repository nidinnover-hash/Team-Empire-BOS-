from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("method", "path", "json_body", "allowed"),
    [
        ("GET", "/api/v1/integrations", None, {200}),
        ("GET", "/api/v1/integrations/ai/status", None, {200}),
        ("POST", "/api/v1/integrations/connect", {}, {422}),
        ("POST", "/api/v1/integrations/clickup/connect", {}, {422}),
        ("POST", "/api/v1/integrations/github/connect", {}, {422}),
        ("POST", "/api/v1/integrations/slack/connect", {}, {422}),
        ("POST", "/api/v1/integrations/digitalocean/connect", {}, {422}),
        ("POST", "/api/v1/integrations/clickup/sync", None, {200, 400, 404, 502}),
        ("POST", "/api/v1/integrations/github/sync", None, {200, 400, 404, 502}),
        ("POST", "/api/v1/integrations/slack/sync", None, {200, 400, 404, 502}),
        ("POST", "/api/v1/integrations/digitalocean/sync", None, {200, 400, 404, 502}),
        ("POST", "/api/v1/integrations/google-calendar/sync", None, {200, 400, 404, 502}),
        ("GET", "/api/v1/email/health", None, {200}),
        ("POST", "/api/v1/email/sync", None, {200, 502}),
    ],
)
async def test_button_backed_endpoints_exist_and_return_expected_status(
    client,
    method: str,
    path: str,
    json_body: dict | None,
    allowed: set[int],
):
    if method == "GET":
        response = await client.get(path)
    else:
        if json_body is None:
            response = await client.post(path)
        else:
            response = await client.post(path, json=json_body)
    assert response.status_code in allowed
    # All responses must be valid JSON (not empty body except 204)
    if response.status_code != 204:
        body = response.json()
        assert isinstance(body, dict | list), f"Unexpected response type {type(body)} from {path}"


# ── Response shape assertions for key GET endpoints ──────────────────────────


async def test_list_integrations_returns_list(client):
    response = await client.get("/api/v1/integrations")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for item in body:
        assert "id" in item
        assert "type" in item
        assert "status" in item


async def test_ai_status_returns_list_of_providers(client):
    response = await client.get("/api/v1/integrations/ai/status")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for item in body:
        assert "provider" in item
        assert "configured" in item
        assert isinstance(item["configured"], bool)


async def test_email_health_returns_dict(client):
    response = await client.get("/api/v1/email/health")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
