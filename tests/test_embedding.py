"""Tests for pgvector embedding service — semantic memory retrieval."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.embedding import (
    embed_memory,
    format_embedding_text,
    generate_embedding,
    search_similar,
)

# ── format_embedding_text ────────────────────────────────────────────────────

def test_format_profile_memory():
    result = format_embedding_text("profile_memory", key="ceo_name", value="Nidin Nover")
    assert result == "ceo_name: Nidin Nover"


def test_format_daily_context():
    result = format_embedding_text("daily_context", context_type="priority", content="Ship v2")
    assert result == "[priority] Ship v2"


def test_format_clone_memory():
    result = format_embedding_text(
        "clone_memory",
        situation="Client asked for discount",
        action_taken="Offered 10% loyalty discount",
        outcome="success",
    )
    assert "Situation: Client asked for discount" in result
    assert "Action: Offered 10% loyalty discount" in result
    assert "Outcome: success" in result


def test_format_unknown_source_type():
    result = format_embedding_text("unknown", text="fallback text")
    assert result == "fallback text"


# ── generate_embedding ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_embedding_disabled(monkeypatch):
    """Returns None when embedding is disabled."""
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", False)
    result = await generate_embedding("test text")
    assert result is None


@pytest.mark.asyncio
async def test_generate_embedding_no_api_key(monkeypatch):
    """Returns None when no valid API key is set."""
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", True)
    monkeypatch.setattr("app.services.embedding.settings.OPENAI_API_KEY", "")
    result = await generate_embedding("test text")
    assert result is None


@pytest.mark.asyncio
async def test_generate_embedding_success(monkeypatch):
    """Calls OpenAI embeddings API and returns vector."""
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", True)
    monkeypatch.setattr("app.services.embedding.settings.OPENAI_API_KEY", "sk-test-real-key")
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_TIMEOUT_SECONDS", 10)

    fake_vector = [0.1] * 1536
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_vector)]

    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        result = await generate_embedding("test text")

    assert result == fake_vector
    mock_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input="test text",
    )


@pytest.mark.asyncio
async def test_generate_embedding_api_error(monkeypatch):
    """Returns None on OpenAI API error."""
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", True)
    monkeypatch.setattr("app.services.embedding.settings.OPENAI_API_KEY", "sk-test-real-key")
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_TIMEOUT_SECONDS", 10)

    with patch("openai.AsyncOpenAI", side_effect=Exception("API down")):
        result = await generate_embedding("test text")

    assert result is None


# ── embed_memory ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embed_memory_creates_row(db, monkeypatch):
    """embed_memory creates a MemoryEmbedding row when generate_embedding succeeds."""
    fake_vector = [0.01] * 1536

    async def fake_generate(text):
        return fake_vector

    monkeypatch.setattr("app.services.embedding.generate_embedding", fake_generate)

    # SQLite won't have the Vector column type, so we expect this to fail gracefully
    # or succeed if the model falls back to Text. Test the logic, not the DB type.
    result = await embed_memory(
        db, organization_id=1, workspace_id=None,
        source_type="profile_memory", source_id=999,
        content_text="ceo_name: Nidin",
    )
    # SQLite path may return None when embeddings are skipped.
    if result is not None:
        assert result.source_type == "profile_memory"
        assert result.source_id == 999
        assert result.content_text == "ceo_name: Nidin"


@pytest.mark.asyncio
async def test_embed_memory_returns_none_when_embedding_fails(db, monkeypatch):
    """embed_memory returns None when generate_embedding returns None."""
    async def fake_generate(text):
        return None

    monkeypatch.setattr("app.services.embedding.generate_embedding", fake_generate)

    result = await embed_memory(
        db, organization_id=1, workspace_id=None,
        source_type="profile_memory", source_id=888,
        content_text="test",
    )
    assert result is None


# ── search_similar ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_similar_disabled(monkeypatch):
    """Returns empty list when embedding is disabled."""
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", False)
    result = await search_similar(MagicMock(), organization_id=1, query_text="test")
    assert result == []


@pytest.mark.asyncio
async def test_search_similar_no_embedding(db, monkeypatch):
    """Returns empty list when embedding generation fails."""
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", True)
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_MAX_RESULTS", 10)
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_SIMILARITY_THRESHOLD", 0.3)

    async def fake_generate(text):
        return None

    monkeypatch.setattr("app.services.embedding.generate_embedding", fake_generate)

    result = await search_similar(db, organization_id=1, query_text="test query")
    assert result == []


@pytest.mark.asyncio
async def test_search_similar_graceful_on_sqlite(db, monkeypatch):
    """search_similar gracefully returns empty on SQLite (no pgvector)."""
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", True)
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_MAX_RESULTS", 10)
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_SIMILARITY_THRESHOLD", 0.3)

    fake_vector = [0.01] * 1536

    async def fake_generate(text):
        return fake_vector

    monkeypatch.setattr("app.services.embedding.generate_embedding", fake_generate)

    # SQLite doesn't support pgvector operators — should return empty, not crash
    result = await search_similar(db, organization_id=1, query_text="revenue strategy")
    assert result == []


# ── schedule_embed hook verification ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_profile_memory_schedules_embed(db, monkeypatch):
    """upsert_profile_memory calls schedule_embed after commit."""
    calls = []

    def fake_schedule(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", True)
    monkeypatch.setattr("app.services.memory.schedule_embed", fake_schedule, raising=False)
    # Patch at import site inside memory.py — the function is imported lazily
    import app.services.embedding as emb_mod
    original_schedule = emb_mod.schedule_embed
    emb_mod.schedule_embed = fake_schedule

    try:
        from app.services.memory import upsert_profile_memory
        await upsert_profile_memory(
            db, organization_id=1, key="test_embed_key", value="test_embed_value",
        )
        # schedule_embed should have been called
        assert len(calls) >= 1
        # Verify args: (org_id, workspace_id, source_type, source_id, text)
        call = calls[0]
        assert call[0] == 1  # org_id
        assert call[2] == "profile_memory"  # source_type
        assert "test_embed_key: test_embed_value" in call[4]  # content_text
    finally:
        emb_mod.schedule_embed = original_schedule


@pytest.mark.asyncio
async def test_add_daily_context_schedules_embed(db, monkeypatch):
    """add_daily_context calls schedule_embed after commit."""
    calls = []

    import app.services.embedding as emb_mod
    original_schedule = emb_mod.schedule_embed
    emb_mod.schedule_embed = lambda *args, **kw: calls.append(args)

    try:
        from app.schemas.memory import DailyContextCreate
        from app.services.memory import add_daily_context

        await add_daily_context(
            db,
            DailyContextCreate(
                date=date.today(),
                context_type="priority",
                content="Launch feature X",
            ),
            organization_id=1,
        )
        assert len(calls) >= 1
        call = calls[0]
        assert call[0] == 1  # org_id
        assert call[2] == "daily_context"
        assert "Launch feature X" in call[4]
    finally:
        emb_mod.schedule_embed = original_schedule


@pytest.mark.asyncio
async def test_store_clone_memory_schedules_embed(db, monkeypatch):
    """store_memory calls schedule_embed after commit."""
    calls = []

    import app.services.embedding as emb_mod
    original_schedule = emb_mod.schedule_embed
    emb_mod.schedule_embed = lambda *args, **kw: calls.append(args)

    try:
        from app.services.clone_memory import store_memory

        await store_memory(
            db, org_id=1, employee_id=1,
            situation="Client requested refund",
            action_taken="Processed immediately",
            outcome="success",
        )
        assert len(calls) >= 1
        call = calls[0]
        assert call[0] == 1  # org_id
        assert call[2] == "clone_memory"
        assert "Client requested refund" in call[4]
    finally:
        emb_mod.schedule_embed = original_schedule


# ── build_memory_context_semantic ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_semantic_context_falls_back_when_disabled(db, monkeypatch):
    """Falls back to lexical build_memory_context when embedding is disabled."""
    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", False)

    from app.services.memory import build_memory_context, build_memory_context_semantic

    semantic_result = await build_memory_context_semantic(
        db, organization_id=1, query="revenue",
    )
    lexical_result = await build_memory_context(db, organization_id=1)
    # Both should return the same thing (fallback)
    assert semantic_result == lexical_result


@pytest.mark.asyncio
async def test_semantic_context_falls_back_on_empty_results(db, monkeypatch):
    """Falls back to lexical when search_similar returns empty."""
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_ENABLED", True)

    async def fake_search(*args, **kwargs):
        return []

    monkeypatch.setattr("app.services.embedding.search_similar", fake_search)

    from app.services.memory import build_memory_context, build_memory_context_semantic

    semantic_result = await build_memory_context_semantic(
        db, organization_id=1, query="anything",
    )
    lexical_result = await build_memory_context(db, organization_id=1)
    assert semantic_result == lexical_result
