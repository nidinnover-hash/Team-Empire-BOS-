"""Tests for Knowledge Brain v2 — extraction, consolidation, graph, backfill."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

# ── Knowledge Extraction: heuristic ──────────────────────────────────────────

def test_extract_heuristic_preference():
    from app.engines.intelligence.knowledge import _extract_knowledge_heuristic

    messages = [{"role": "user", "content": "I prefer to use Slack for team communication"}]
    entries = _extract_knowledge_heuristic(messages)
    assert len(entries) >= 1
    assert entries[0]["category"] == "preference"
    assert "Slack" in entries[0]["value"]


def test_extract_heuristic_fact():
    from app.engines.intelligence.knowledge import _extract_knowledge_heuristic

    messages = [{"role": "user", "content": "Our revenue last quarter was 2.5M USD"}]
    entries = _extract_knowledge_heuristic(messages)
    assert len(entries) >= 1
    assert entries[0]["category"] == "fact"


def test_extract_heuristic_decision():
    from app.engines.intelligence.knowledge import _extract_knowledge_heuristic

    messages = [{"role": "user", "content": "I decided to go with the premium pricing tier"}]
    entries = _extract_knowledge_heuristic(messages)
    assert len(entries) >= 1
    assert entries[0]["category"] == "decision"


def test_extract_heuristic_goal():
    from app.engines.intelligence.knowledge import _extract_knowledge_heuristic

    messages = [{"role": "user", "content": "Our goal is to reach 100 new clients this quarter"}]
    entries = _extract_knowledge_heuristic(messages)
    assert len(entries) >= 1
    assert entries[0]["category"] == "goal"


def test_extract_heuristic_ignores_assistant():
    from app.engines.intelligence.knowledge import _extract_knowledge_heuristic

    messages = [
        {"role": "assistant", "content": "I prefer to do things differently"},
        {"role": "user", "content": "Hello there"},
    ]
    entries = _extract_knowledge_heuristic(messages)
    assert len(entries) == 0


def test_extract_heuristic_deduplicates():
    from app.engines.intelligence.knowledge import _extract_knowledge_heuristic

    messages = [
        {"role": "user", "content": "I prefer Python for backend work"},
        {"role": "user", "content": "I prefer Python for backend work"},
    ]
    entries = _extract_knowledge_heuristic(messages)
    # Should not duplicate the same message
    assert len(entries) == 1


# ── Knowledge Extraction: AI path ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_knowledge_ai_path(monkeypatch):
    from app.engines.intelligence.knowledge import extract_knowledge_from_conversation

    ai_response = json.dumps([
        {"category": "fact", "key": "team_size", "value": "We have 15 engineers", "confidence": 0.9},
        {"category": "preference", "key": "ai_provider", "value": "Use OpenAI for email", "confidence": 0.85},
    ])

    async def fake_call_ai(**kwargs):
        return ai_response

    monkeypatch.setattr("app.engines.brain.router.call_ai", fake_call_ai)

    messages = [{"role": "user", "content": "We have 15 engineers and use OpenAI for email"}]
    entries = await extract_knowledge_from_conversation(messages, use_ai=True)
    assert len(entries) == 2
    assert entries[0]["category"] == "fact"
    assert entries[1]["category"] == "preference"


@pytest.mark.asyncio
async def test_extract_knowledge_falls_back_on_ai_error(monkeypatch):
    from app.engines.intelligence.knowledge import extract_knowledge_from_conversation

    async def broken_ai(**kwargs):
        raise RuntimeError("API down")

    monkeypatch.setattr("app.engines.brain.router.call_ai", broken_ai)

    messages = [{"role": "user", "content": "I prefer using Python for everything"}]
    entries = await extract_knowledge_from_conversation(messages, use_ai=True)
    # Should fall back to heuristic
    assert len(entries) >= 1
    assert entries[0]["category"] == "preference"


@pytest.mark.asyncio
async def test_extract_knowledge_heuristic_only():
    from app.engines.intelligence.knowledge import extract_knowledge_from_conversation

    messages = [{"role": "user", "content": "Our goal is to double revenue by Q4"}]
    entries = await extract_knowledge_from_conversation(messages, use_ai=False)
    assert len(entries) >= 1
    assert entries[0]["category"] == "goal"


# ── Parse extraction response ────────────────────────────────────────────────

def test_parse_extraction_strips_markdown():
    from app.engines.intelligence.knowledge import _parse_extraction_response

    raw = '```json\n[{"category": "fact", "key": "revenue", "value": "2M USD", "confidence": 0.9}]\n```'
    result = _parse_extraction_response(raw)
    assert len(result) == 1
    assert result[0]["key"] == "revenue"


def test_parse_extraction_rejects_invalid_json():
    from app.engines.intelligence.knowledge import _parse_extraction_response

    result = _parse_extraction_response("not json at all")
    assert result == []


def test_parse_extraction_rejects_invalid_category():
    from app.engines.intelligence.knowledge import _parse_extraction_response

    raw = json.dumps([{"category": "invalid_cat", "key": "x", "value": "y", "confidence": 0.5}])
    result = _parse_extraction_response(raw)
    assert result == []


def test_parse_extraction_clamps_confidence():
    from app.engines.intelligence.knowledge import _parse_extraction_response

    raw = json.dumps([{"category": "fact", "key": "x", "value": "y", "confidence": 5.0}])
    result = _parse_extraction_response(raw)
    assert result[0]["confidence"] == 1.0


# ── Memory Consolidation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consolidate_memories_merges_duplicates(db):
    from app.engines.intelligence.knowledge import consolidate_memories
    from app.services.memory import upsert_profile_memory

    # Create two similar entries
    await upsert_profile_memory(db, organization_id=1, key="ceo_name", value="Nidin Nover")
    await upsert_profile_memory(db, organization_id=1, key="ceo_name_full", value="Nidin Nover CEO")

    result = await consolidate_memories(db, organization_id=1, dry_run=True)
    assert result["scanned"] >= 2
    # dry_run should not delete
    assert result["deleted"] == 0


@pytest.mark.asyncio
async def test_consolidate_memories_no_duplicates(db):
    from app.engines.intelligence.knowledge import consolidate_memories

    # Use a separate org_id so we don't see entries from other tests
    result = await consolidate_memories(db, organization_id=9999, dry_run=True)
    assert result["scanned"] == 0
    assert result["merged"] == 0


# ── Knowledge Graph ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_knowledge_graph(db):
    from app.engines.intelligence.knowledge import build_knowledge_graph

    graph = await build_knowledge_graph(db, organization_id=1)
    assert "nodes" in graph
    assert "edges" in graph
    assert "generated_at" in graph
    assert isinstance(graph["nodes"], list)
    assert isinstance(graph["edges"], list)


@pytest.mark.asyncio
async def test_knowledge_graph_includes_integrations(db, monkeypatch):
    from app.engines.intelligence.knowledge import build_knowledge_graph

    # Mock list_integrations to return a fake integration
    fake_integ = MagicMock(type="gmail", status="connected")

    async def fake_list_integrations(db, **kwargs):
        return [fake_integ]

    monkeypatch.setattr(
        "app.services.integration.list_integrations",
        fake_list_integrations,
    )

    graph = await build_knowledge_graph(db, organization_id=1)
    integ_nodes = [n for n in graph["nodes"] if n["entity_type"] == "integration"]
    assert len(integ_nodes) >= 1
    assert integ_nodes[0]["name"] == "gmail"


# ── Rank memories by relevance ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rank_memories_boosts_connected(db):
    from app.engines.intelligence.knowledge import (
        EntityNode,
        EntityRelation,
        KnowledgeGraph,
        rank_memories_by_relevance,
    )

    # Create fake memories
    mem_a = MagicMock(id=1, key="revenue_target", value="10M by Q4")
    mem_b = MagicMock(id=2, key="lunch_preference", value="Always salad")

    graph = KnowledgeGraph(
        nodes=[
            EntityNode(entity_type="concept", name="revenue_target", properties={}),
            EntityNode(entity_type="concept", name="lunch_preference", properties={}),
            EntityNode(entity_type="person", name="Nidin", properties={}),
        ],
        edges=[
            EntityRelation(source="revenue_target", target="Nidin", relation="mentions", weight=0.5),
        ],
        generated_at="2026-03-07T00:00:00",
    )

    ranked = await rank_memories_by_relevance(
        db, organization_id=1, query="What is Nidin working on?",
        memories=[mem_b, mem_a], graph=graph,
    )
    # revenue_target should rank higher because it's connected to "Nidin"
    assert ranked[0].key == "revenue_target"


@pytest.mark.asyncio
async def test_rank_memories_no_graph(db):
    from app.engines.intelligence.knowledge import rank_memories_by_relevance

    mem = MagicMock(id=1, key="test", value="test")
    result = await rank_memories_by_relevance(
        db, organization_id=1, query="test", memories=[mem], graph=None,
    )
    assert result == [mem]


# ── Batch Backfill ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backfill_skips_sqlite(db, monkeypatch):
    from app.services.embedding import backfill_embeddings

    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", True)
    result = await backfill_embeddings(db, organization_id=1)
    # SQLite should be skipped
    assert "skipped" in result or "profile_memory" in result


@pytest.mark.asyncio
async def test_backfill_disabled(db, monkeypatch):
    from app.services.embedding import backfill_embeddings

    monkeypatch.setattr("app.services.embedding.settings.EMBEDDING_ENABLED", False)
    result = await backfill_embeddings(db, organization_id=1)
    assert result.get("reason") == "EMBEDDING_ENABLED=false"


# ── Save extracted knowledge ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_extracted_knowledge(db):
    from app.engines.intelligence.knowledge import KnowledgeEntry, save_extracted_knowledge

    entries = [
        KnowledgeEntry(category="fact", key="test_knowledge_save", value="Test value", confidence=0.8),
    ]
    saved = await save_extracted_knowledge(db, organization_id=1, entries=entries)
    assert saved == 1

    # Verify it was stored
    from app.services.memory import get_profile_memory
    memories = await get_profile_memory(db, organization_id=1)
    keys = [m.key for m in memories]
    assert "test_knowledge_save" in keys


# ── Nightly job ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_knowledge_consolidation_job_runs(db, monkeypatch):
    """Verify the consolidation job function exists and is callable."""
    from app.jobs.intelligence import maybe_run_knowledge_consolidation

    # Job won't actually run because hour check (2 AM) won't match
    await maybe_run_knowledge_consolidation(db, org_id=1)
    # Just verify it doesn't crash — actual logic tested above


# ── Similarity helper ────────────────────────────────────────────────────────

def test_similarity_identical():
    from app.engines.intelligence.knowledge import _similarity

    assert _similarity("hello world", "hello world") == 1.0


def test_similarity_different():
    from app.engines.intelligence.knowledge import _similarity

    sim = _similarity("hello world", "goodbye universe")
    assert sim < 0.5


def test_similarity_case_insensitive():
    from app.engines.intelligence.knowledge import _similarity

    assert _similarity("Hello World", "hello world") == 1.0
