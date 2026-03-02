"""Tests for POST /api/v1/integrations/ai/chat and GET /ai/models endpoints."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

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


# ── GET /ai/models ────────────────────────────────────────────────────────────


async def test_ai_models_returns_all_providers(client, monkeypatch):
    monkeypatch.setattr(ai_router, "_get_key", lambda p, org_id=1: "sk-test" if p == "openai" else None)
    resp = await client.get("/api/v1/integrations/ai/models", headers=_ceo_headers())
    assert resp.status_code == 200
    data = resp.json()
    providers = [item["provider"] for item in data]
    assert "openai" in providers
    assert "anthropic" in providers
    assert "groq" in providers
    assert "gemini" in providers


async def test_ai_models_shows_configured_status(client, monkeypatch):
    monkeypatch.setattr(ai_router, "_get_key", lambda p, org_id=1: "sk-test" if p == "openai" else None)
    resp = await client.get("/api/v1/integrations/ai/models", headers=_ceo_headers())
    data = resp.json()
    openai_entry = next(item for item in data if item["provider"] == "openai")
    assert openai_entry["configured"] is True
    anthropic_entry = next(item for item in data if item["provider"] == "anthropic")
    assert anthropic_entry["configured"] is False


async def test_ai_models_includes_model_list(client, monkeypatch):
    monkeypatch.setattr(ai_router, "_get_key", lambda p, org_id=1: "sk-test")
    resp = await client.get("/api/v1/integrations/ai/models", headers=_staff_headers())
    assert resp.status_code == 200
    data = resp.json()
    openai_entry = next(item for item in data if item["provider"] == "openai")
    assert "gpt-4o" in openai_entry["models"]
    assert openai_entry["default_model"]  # non-empty


# ── POST /ai/chat (non-streaming) ─────────────────────────────────────────────


async def test_ai_chat_non_streaming(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Hello from OpenAI!"

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": "Hello", "provider": "openai", "stream": False},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "openai"
    assert body["response"] == "Hello from OpenAI!"
    assert "model" in body


async def test_ai_chat_anthropic_non_streaming(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Hello from Claude!"

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": "Hello", "provider": "anthropic", "stream": False},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "anthropic"
    assert body["response"] == "Hello from Claude!"


async def test_ai_chat_claude_alias(client, monkeypatch):
    """'claude' should be normalized to 'anthropic'."""
    async def _fake_call_ai(**kwargs):
        assert kwargs.get("provider") == "anthropic"
        return "From Claude."

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": "Hi", "provider": "anthropic", "stream": False},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200


async def test_ai_chat_rejects_invalid_model(client, monkeypatch):
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": "Hello", "provider": "openai", "model": "nonexistent-model"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 400
    assert "not available" in resp.json()["detail"]


async def test_ai_chat_default_provider(client, monkeypatch):
    async def _fake_call_ai(**kwargs):
        return "Default response."

    monkeypatch.setattr(ai_router, "call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": "Hello"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Default response."


async def test_ai_chat_max_tokens_limit(client):
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": "Hi", "max_tokens": 99999},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 422  # validation error


async def test_ai_chat_empty_message_rejected(client):
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": ""},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 422


# ── POST /ai/chat (streaming) ─────────────────────────────────────────────────


async def test_ai_chat_streaming_returns_sse(client, monkeypatch):
    async def _fake_stream(**kwargs):
        yield "Hello "
        yield "world!"

    monkeypatch.setattr(ai_router, "stream_ai", _fake_stream)
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": "Hello", "provider": "openai", "stream": True},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    text = resp.text
    assert "data:" in text
    assert "[DONE]" in text


async def test_ai_chat_streaming_content(client, monkeypatch):
    chunks = ["The ", "quick ", "brown ", "fox."]

    async def _fake_stream(**kwargs):
        for c in chunks:
            yield c

    monkeypatch.setattr(ai_router, "stream_ai", _fake_stream)
    resp = await client.post(
        "/api/v1/integrations/ai/chat",
        json={"message": "Tell me a story", "provider": "openai", "stream": True},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    # Parse SSE lines
    lines = resp.text.strip().split("\n")
    collected = []
    for line in lines:
        if line.startswith("data: ") and "[DONE]" not in line:
            payload = json.loads(line[6:])
            collected.append(payload["text"])
    assert "".join(collected) == "The quick brown fox."


# ── AVAILABLE_MODELS ──────────────────────────────────────────────────────────


def test_available_models_structure():
    assert "openai" in ai_router.AVAILABLE_MODELS
    assert "anthropic" in ai_router.AVAILABLE_MODELS
    assert "groq" in ai_router.AVAILABLE_MODELS
    assert "gemini" in ai_router.AVAILABLE_MODELS
    for provider, models in ai_router.AVAILABLE_MODELS.items():
        assert isinstance(models, list)
        assert len(models) > 0
        for m in models:
            assert isinstance(m, str)


# ── stream_ai function ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_ai_yields_chunks(monkeypatch):
    async def _fake_stream_openai(system_prompt, user_message, max_tokens, model=None, conversation_history=None, org_id=1):
        yield "chunk1"
        yield "chunk2"

    monkeypatch.setattr(ai_router, "_stream_openai", _fake_stream_openai)
    collected = []
    async for chunk in ai_router.stream_ai(
        system_prompt="Test",
        user_message="Hello",
        provider="openai",
    ):
        collected.append(chunk)
    assert collected == ["chunk1", "chunk2"]


@pytest.mark.asyncio
async def test_stream_ai_claude_alias(monkeypatch):
    async def _fake_stream_anthropic(system_prompt, user_message, max_tokens, model=None, conversation_history=None, org_id=1):
        yield "claude-response"

    monkeypatch.setattr(ai_router, "_stream_anthropic", _fake_stream_anthropic)
    collected = []
    async for chunk in ai_router.stream_ai(
        system_prompt="Test",
        user_message="Hello",
        provider="claude",
    ):
        collected.append(chunk)
    assert collected == ["claude-response"]
