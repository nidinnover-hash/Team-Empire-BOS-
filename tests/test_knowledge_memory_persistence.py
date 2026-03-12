"""Tests for knowledge extraction persistence: save_extracted_knowledge partial/total failure behavior."""
from unittest.mock import AsyncMock, patch

import pytest

from app.engines.intelligence.knowledge import save_extracted_knowledge


@pytest.mark.asyncio
async def test_save_extracted_knowledge_partial_failure_returns_count_and_does_not_raise(db):
    """When some upserts fail, return count of successes and do not raise."""
    entries = [
        {"category": "fact", "key": "k1", "value": "v1", "confidence": 0.9},
        {"category": "fact", "key": "k2", "value": "v2", "confidence": 0.8},
    ]
    call_count = 0

    async def mock_upsert(db, *, organization_id, key, value, category, workspace_id=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated failure")
        return None

    with patch("app.services.memory.upsert_profile_memory", side_effect=mock_upsert):
        saved = await save_extracted_knowledge(db, organization_id=1, entries=entries)

    assert saved == 1
    assert call_count == 2


@pytest.mark.asyncio
async def test_save_extracted_knowledge_total_failure_raises_runtime_error(db):
    """When every upsert fails, raise RuntimeError with org id in message."""
    entries = [
        {"category": "fact", "key": "k1", "value": "v1", "confidence": 0.9},
    ]

    async def mock_upsert_fail(*args, **kwargs):
        raise RuntimeError("simulated failure")

    with patch("app.services.memory.upsert_profile_memory", side_effect=mock_upsert_fail), pytest.raises(RuntimeError, match=r"Failed to persist any knowledge entries for org 1"):
        await save_extracted_knowledge(db, organization_id=1, entries=entries)


@pytest.mark.asyncio
async def test_save_extracted_knowledge_all_success_returns_count(db):
    """When all upserts succeed, return full count."""
    entries = [
        {"category": "fact", "key": "a", "value": "b", "confidence": 0.7},
        {"category": "preference", "key": "c", "value": "d", "confidence": 0.8},
    ]

    with patch("app.services.memory.upsert_profile_memory", new_callable=AsyncMock, return_value=None):
        saved = await save_extracted_knowledge(db, organization_id=1, entries=entries)

    assert saved == 2
