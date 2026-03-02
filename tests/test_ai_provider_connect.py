"""Tests for POST /api/v1/integrations/ai/{provider}/connect endpoint."""
from app.core.security import create_access_token
from app.services import ai_router


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


def _staff_headers() -> dict:
    token = create_access_token(
        {"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": 1}
    )
    return {"Authorization": f"Bearer {token}"}


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_ai_connect_openai_success(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Connected."

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)

    resp = await client.post(
        "/api/v1/integrations/ai/openai/connect",
        json={"api_key": "sk-test-key-12345"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["provider"] == "openai"
    assert body["status"] == "connected"
    assert "validated" in body["message"].lower()


async def test_ai_connect_anthropic_success(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Connected."

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)

    resp = await client.post(
        "/api/v1/integrations/ai/anthropic/connect",
        json={"api_key": "sk-ant-test-key"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 201
    assert resp.json()["provider"] == "anthropic"


async def test_ai_connect_groq_success(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Connected."

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)

    resp = await client.post(
        "/api/v1/integrations/ai/groq/connect",
        json={"api_key": "gsk_test-key"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 201
    assert resp.json()["provider"] == "groq"


async def test_ai_connect_gemini_success(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Connected."

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)

    resp = await client.post(
        "/api/v1/integrations/ai/gemini/connect",
        json={"api_key": "AIza-test-key"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 201
    assert resp.json()["provider"] == "gemini"


# ── Validation failure ────────────────────────────────────────────────────────


async def test_ai_connect_bad_key_returns_400(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Error: Authentication failed."

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)

    resp = await client.post(
        "/api/v1/integrations/ai/openai/connect",
        json={"api_key": "bad-key"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 400
    assert "Error" in resp.json()["detail"]


async def test_ai_connect_clears_cache_on_failure(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Error: Invalid key."

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)

    # Pre-seed cache
    ai_router.set_ai_key_cache("openai", "bad-key", org_id=1)

    resp = await client.post(
        "/api/v1/integrations/ai/openai/connect",
        json={"api_key": "bad-key"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 400
    # Cache should be cleared after failure
    assert ai_router._ai_key_cache.get(("openai", 1)) is None


# ── Invalid provider ──────────────────────────────────────────────────────────


async def test_ai_connect_invalid_provider_returns_422(client):
    resp = await client.post(
        "/api/v1/integrations/ai/invalid_provider/connect",
        json={"api_key": "sk-test"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 422


# ── RBAC ──────────────────────────────────────────────────────────────────────


async def test_ai_connect_denied_for_staff(client, monkeypatch):
    resp = await client.post(
        "/api/v1/integrations/ai/openai/connect",
        json={"api_key": "sk-test"},
        headers=_staff_headers(),
    )
    assert resp.status_code == 403


# ── Schema validation ─────────────────────────────────────────────────────────


async def test_ai_connect_missing_key_returns_422(client):
    resp = await client.post(
        "/api/v1/integrations/ai/openai/connect",
        json={},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 422


async def test_ai_connect_key_too_short_returns_422(client):
    resp = await client.post(
        "/api/v1/integrations/ai/openai/connect",
        json={"api_key": "x"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 422


# ── Key cache helpers ─────────────────────────────────────────────────────────


async def test_set_and_clear_ai_key_cache():
    ai_router.set_ai_key_cache("test_provider", "test_key", org_id=1)
    cached_key, cached_expiry = ai_router._ai_key_cache[("test_provider", 1)]
    assert cached_key == "test_key"
    assert isinstance(cached_expiry, float)

    ai_router.clear_ai_key_cache("test_provider", org_id=1)
    assert ("test_provider", 1) not in ai_router._ai_key_cache


async def test_get_key_checks_cache_first(monkeypatch):
    monkeypatch.setattr(ai_router.settings, "OPENAI_API_KEY", "env-key")
    ai_router.set_ai_key_cache("openai", "cached-key", org_id=1)
    try:
        key = ai_router._get_key("openai", org_id=1)
        assert key == "cached-key"
    finally:
        ai_router.clear_ai_key_cache("openai", org_id=1)


async def test_get_key_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(ai_router.settings, "OPENAI_API_KEY", "env-key")
    ai_router.clear_ai_key_cache("openai", org_id=1)
    key = ai_router._get_key("openai", org_id=1)
    assert key == "env-key"


# ── /ai/status reflects cache ────────────────────────────────────────────────


async def test_ai_status_shows_cached_key_as_configured(client, monkeypatch):
    monkeypatch.setattr(ai_router.settings, "OPENAI_API_KEY", None)
    ai_router.set_ai_key_cache("openai", "cached-real-key", org_id=1)
    try:
        resp = await client.get(
            "/api/v1/integrations/ai/status",
            headers=_ceo_headers(),
        )
        assert resp.status_code == 200
        providers = {p["provider"]: p for p in resp.json()}
        assert providers["openai"]["configured"] is True
    finally:
        ai_router.clear_ai_key_cache("openai", org_id=1)


# ── /ai/test uses unified key resolution ─────────────────────────────────────


async def test_ai_test_not_configured_message_includes_connect_hint(client, monkeypatch):
    monkeypatch.setattr(ai_router.settings, "OPENAI_API_KEY", None)
    ai_router.clear_ai_key_cache("openai", org_id=1)

    resp = await client.post(
        "/api/v1/integrations/ai/test?provider=openai",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "not_configured"
    assert "/connect" in body["message"]
