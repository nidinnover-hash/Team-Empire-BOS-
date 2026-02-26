"""Tests for app/services/data_collection/ingest.py — data ingestion and clone pro training."""
from datetime import date

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.schemas.data_collection import (
    CloneProTrainingRequest,
    DataCollectRequest,
)
from app.services.data_collection.ingest import ingest_data, train_clone_pro


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


# ── ingest_data ───────────────────────────────────────────────────────────────


async def test_ingest_notes_default(client):
    """Default target ingests content as notes."""
    session, agen = await _get_session()
    try:
        result = await ingest_data(
            session,
            org_id=1,
            data=DataCollectRequest(
                content="Test note from ingestion pipeline",
                source="manual",
            ),
        )
        assert result.target == "notes"
        assert result.ingested_count == 1
        assert len(result.created_ids) == 1
    finally:
        await agen.aclose()


async def test_ingest_empty_content(client):
    """Empty content returns zero ingested."""
    session, agen = await _get_session()
    try:
        result = await ingest_data(
            session,
            org_id=1,
            data=DataCollectRequest(
                content="   ",
                source="manual",
            ),
        )
        assert result.ingested_count == 0
    finally:
        await agen.aclose()


async def test_ingest_split_lines(client):
    """Split lines creates multiple entries."""
    session, agen = await _get_session()
    try:
        result = await ingest_data(
            session,
            org_id=1,
            data=DataCollectRequest(
                content="Line 1\nLine 2\nLine 3",
                source="manual",
                split_lines=True,
            ),
        )
        assert result.ingested_count == 3
        assert len(result.created_ids) == 3
    finally:
        await agen.aclose()


async def test_ingest_profile_memory(client):
    """Target=profile_memory stores in profile memory."""
    session, agen = await _get_session()
    try:
        result = await ingest_data(
            session,
            org_id=1,
            data=DataCollectRequest(
                content="I prefer concise responses",
                source="manual",
                target="profile_memory",
                key="preference.response_style",
                category="preferences",
            ),
        )
        assert result.target == "profile_memory"
        assert result.ingested_count == 1
    finally:
        await agen.aclose()


async def test_ingest_profile_memory_split_lines(client):
    """Split lines with profile_memory creates indexed keys."""
    session, agen = await _get_session()
    try:
        result = await ingest_data(
            session,
            org_id=1,
            data=DataCollectRequest(
                content="Item A\nItem B",
                source="manual",
                target="profile_memory",
                key="test.items",
                split_lines=True,
            ),
        )
        assert result.ingested_count == 2
    finally:
        await agen.aclose()


async def test_ingest_profile_memory_missing_key(client):
    """Profile memory without key raises ValueError."""
    import pytest

    session, agen = await _get_session()
    try:
        with pytest.raises(ValueError, match="key is required"):
            await ingest_data(
                session,
                org_id=1,
                data=DataCollectRequest(
                    content="data",
                    source="manual",
                    target="profile_memory",
                ),
            )
    finally:
        await agen.aclose()


async def test_ingest_profile_memory_invalid_key(client):
    """Profile memory with invalid key raises ValueError."""
    import pytest

    session, agen = await _get_session()
    try:
        with pytest.raises(ValueError, match="key must match"):
            await ingest_data(
                session,
                org_id=1,
                data=DataCollectRequest(
                    content="data",
                    source="manual",
                    target="profile_memory",
                    key="a",  # too short
                ),
            )
    finally:
        await agen.aclose()


async def test_ingest_daily_context(client):
    """Target=daily_context stores in daily context."""
    session, agen = await _get_session()
    try:
        result = await ingest_data(
            session,
            org_id=1,
            data=DataCollectRequest(
                content="Focus on shipping v2 today",
                source="manual",
                target="daily_context",
                context_type="priority",
                for_date=date.today(),
            ),
        )
        assert result.target == "daily_context"
        assert result.ingested_count == 1
    finally:
        await agen.aclose()


async def test_ingest_daily_context_invalid_type(client):
    """Invalid context_type raises ValueError."""
    import pytest

    session, agen = await _get_session()
    try:
        with pytest.raises(ValueError, match="context_type must be one of"):
            await ingest_data(
                session,
                org_id=1,
                data=DataCollectRequest(
                    content="data",
                    source="manual",
                    target="daily_context",
                    context_type="invalid_type",
                ),
            )
    finally:
        await agen.aclose()


# ── train_clone_pro ───────────────────────────────────────────────────────────


async def test_train_clone_pro_basic(client):
    """Basic pro training stores profile memory, context, and notes."""
    session, agen = await _get_session()
    try:
        result = await train_clone_pro(
            session,
            org_id=1,
            data=CloneProTrainingRequest(
                preferred_name="Nidin",
                communication_style="Direct and concise",
                top_priorities=["Ship v2", "Hire backend dev"],
                operating_rules=["Never commit untested code"],
                daily_focus=["Review PRs", "Standup at 9am"],
                domain_notes=["FastAPI project with SQLAlchemy async"],
                source="manual",
            ),
        )
        assert result.profile_memory_written >= 5  # name + style + 2 priorities + priority_focus + 1 rule
        assert result.daily_context_written == 2
        assert result.notes_written == 1
        assert len(result.memory_keys) >= 5
    finally:
        await agen.aclose()


async def test_train_clone_pro_no_priorities_raises(client):
    """Pro training without priorities raises ValueError."""
    import pytest

    session, agen = await _get_session()
    try:
        with pytest.raises(ValueError, match="top_priorities"):
            await train_clone_pro(
                session,
                org_id=1,
                data=CloneProTrainingRequest(
                    communication_style="Direct",
                    top_priorities=[],
                    source="manual",
                ),
            )
    finally:
        await agen.aclose()


async def test_train_clone_pro_minimal(client):
    """Minimal pro training with just required fields."""
    session, agen = await _get_session()
    try:
        result = await train_clone_pro(
            session,
            org_id=1,
            data=CloneProTrainingRequest(
                communication_style="Formal",
                top_priorities=["Launch product"],
                source="manual",
            ),
        )
        assert result.profile_memory_written >= 3  # style + 1 priority + priority_focus
        assert result.daily_context_written == 0
        assert result.notes_written == 0
    finally:
        await agen.aclose()
