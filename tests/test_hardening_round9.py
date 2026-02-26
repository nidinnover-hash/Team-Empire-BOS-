"""
Round 9 hardening tests — response models, query bounds, schema validation.
"""
import pytest

# ── ComposeRequest validation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compose_request_rejects_empty_to(client):
    """ComposeRequest.to must have min_length=1."""
    resp = await client.post(
        "/api/v1/email/compose",
        json={"to": "", "subject": "Test", "instruction": "Write a greeting"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compose_request_rejects_empty_subject(client):
    """ComposeRequest.subject must have min_length=1."""
    resp = await client.post(
        "/api/v1/email/compose",
        json={"to": "test@example.com", "subject": "", "instruction": "Write a greeting"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compose_request_rejects_empty_instruction(client):
    """ComposeRequest.instruction must have min_length=1."""
    resp = await client.post(
        "/api/v1/email/compose",
        json={"to": "test@example.com", "subject": "Hi", "instruction": ""},
    )
    assert resp.status_code == 422


# ── Query parameter bounds ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tasks_offset_upper_bound(client):
    """Offset over 10_000 should be rejected."""
    resp = await client.get("/api/v1/tasks", params={"offset": 99999})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tasks_category_max_length(client):
    """Category over 50 chars should be rejected."""
    resp = await client.get("/api/v1/tasks", params={"category": "x" * 51})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_email_inbox_offset_upper_bound(client):
    """Email inbox offset over 10_000 should be rejected."""
    resp = await client.get("/api/v1/email/inbox", params={"offset": 10001})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_notes_offset_upper_bound(client):
    """Notes offset over 10_000 should be rejected."""
    resp = await client.get("/api/v1/notes", params={"offset": 10001})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_projects_offset_upper_bound(client):
    """Projects offset over 10_000 should be rejected."""
    resp = await client.get("/api/v1/projects", params={"offset": 10001})
    assert resp.status_code == 422


# ── Response model shapes ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_me_response_model(client):
    """GET /api/v1/auth/me should return the UserMeRead shape."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "email" in data
    assert "role" in data
    assert "org_id" in data
    # response_model should strip extra fields (e.g., token_version)
    assert "token_version" not in data


@pytest.mark.asyncio
async def test_root_me_response_model(client):
    """GET /me should return the UserMeRead shape."""
    resp = await client.get("/me")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"id", "email", "role", "org_id"}


@pytest.mark.asyncio
async def test_search_response_model(client):
    """GET /api/v1/search should return the SearchResponse shape."""
    resp = await client.get("/api/v1/search", params={"q": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "query" in data
    assert "total" in data
    assert "results" in data
    assert isinstance(data["results"], list)


# ── Webhook parameter bounds ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_whatsapp_webhook_verify_hub_mode_max_length(client):
    """hub.mode over 50 chars should be rejected."""
    resp = await client.get(
        "/api/v1/integrations/whatsapp/webhook",
        params={"hub.mode": "x" * 51, "hub.verify_token": "t", "hub.challenge": "c"},
    )
    assert resp.status_code == 422


# ── Schema imports work ──────────────────────────────────────────────────────


def test_auth_schemas_importable():
    """All auth schemas should be importable."""
    from app.schemas.auth import (
        TokenResponse,
        UserMeRead,
        WebApiTokenResponse,
        WebLoginResponse,
        WebLogoutResponse,
        WebSessionResponse,
    )
    assert TokenResponse(access_token="abc").token_type == "bearer"
    assert UserMeRead(id=1, email="a@b.com", role="CEO", org_id=1).org_id == 1
    assert WebLoginResponse(status="ok", email="a@b.com", role="CEO").status == "ok"
    assert WebLogoutResponse(status="logged_out").status == "logged_out"
    assert WebSessionResponse(logged_in=False).logged_in is False
    assert WebApiTokenResponse(token="abc").token == "abc"


def test_search_schemas_importable():
    """Search schemas should be importable."""
    from app.schemas.search import SearchResponse, SearchResultItem
    item = SearchResultItem(id=1, title="test", type="task")
    resp = SearchResponse(query="q", total=1, results=[item])
    assert resp.total == 1


def test_slack_send_result_importable():
    """SlackSendResult schema should be importable."""
    from app.schemas.integration import SlackSendResult
    r = SlackSendResult(ok=True, ts="123.456")
    assert r.ok is True
