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
        ("POST", "/api/v1/integrations/clickup/sync", None, {200, 400, 404, 502}),
        ("POST", "/api/v1/integrations/github/sync", None, {200, 400, 404, 502}),
        ("POST", "/api/v1/integrations/slack/sync", None, {200, 400, 404, 502}),
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
