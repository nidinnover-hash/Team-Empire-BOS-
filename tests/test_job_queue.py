"""Tests for persistent job queue — enqueue, claim, execute, retry, dead-letter."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.models.job_queue import JobEntry

# ── Model ────────────────────────────────────────────────────────────────────

def test_job_entry_repr():
    job = JobEntry(id=1, job_name="test_job", status="pending")
    assert "test_job" in repr(job)
    assert "pending" in repr(job)


# ── Enqueue ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enqueue_creates_job(db):
    from app.services.job_queue import enqueue

    job_id = await enqueue("test_job", {"key": "value"}, db=db)
    assert job_id is not None

    job = await db.get(JobEntry, job_id)
    assert job is not None
    assert job.job_name == "test_job"
    assert job.status == "pending"
    assert json.loads(job.payload_json) == {"key": "value"}
    assert job.attempts == 0


@pytest.mark.asyncio
async def test_enqueue_with_delay(db):
    from app.services.job_queue import enqueue

    job_id = await enqueue("delayed_job", {}, db=db, delay_seconds=60)
    job = await db.get(JobEntry, job_id)
    assert job is not None
    # run_after should be ~60s in the future
    now = datetime.now(UTC)
    run_after = job.run_after.replace(tzinfo=UTC) if job.run_after.tzinfo is None else job.run_after
    assert run_after > now


@pytest.mark.asyncio
async def test_enqueue_with_priority(db):
    from app.services.job_queue import enqueue

    id1 = await enqueue("low_prio", {}, db=db, priority=0)
    id2 = await enqueue("high_prio", {}, db=db, priority=10)
    job1 = await db.get(JobEntry, id1)
    job2 = await db.get(JobEntry, id2)
    assert job1.priority == 0
    assert job2.priority == 10


# ── Handler Registration ────────────────────────────────────────────────────

def test_register_handler():
    from app.services.job_queue import _handlers, register_handler

    async def my_handler(**kwargs):
        pass

    register_handler("test_register", my_handler)
    assert "test_register" in _handlers
    _handlers.pop("test_register", None)


def test_handler_decorator():
    from app.services.job_queue import _handlers, handler

    @handler("test_decorated")
    async def my_handler(**kwargs):
        pass

    assert "test_decorated" in _handlers
    _handlers.pop("test_decorated", None)


# ── Execute Job ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_job_calls_handler(db):
    """Handler is called with payload kwargs when job executes."""
    from app.services.job_queue import _execute_job, _handlers, enqueue

    calls = []

    async def success_handler(**kwargs):
        calls.append(kwargs)

    _handlers["test_exec_handler"] = success_handler
    try:
        job_id = await enqueue("test_exec_handler", {"foo": "bar"}, db=db)
        await db.commit()

        job = await db.get(JobEntry, job_id)
        job.status = "running"
        job.attempts = 1
        await db.commit()
        await db.refresh(job)

        # Mock get_session_factory to return a factory that yields the test db's bind
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        test_factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)

        with patch("app.db.session.get_session_factory", return_value=test_factory):
            await _execute_job(job)

        assert len(calls) == 1
        assert calls[0] == {"foo": "bar"}

        # Job should be marked completed
        await db.refresh(job)
        assert job.status == "completed"
    finally:
        _handlers.pop("test_exec_handler", None)


@pytest.mark.asyncio
async def test_execute_job_no_handler(db):
    """Job with no registered handler is marked as dead."""
    from app.services.job_queue import _execute_job, enqueue

    job_id = await enqueue("nonexistent_handler", {}, db=db)
    await db.commit()

    job = await db.get(JobEntry, job_id)
    job.status = "running"
    job.attempts = 1
    await db.commit()
    await db.refresh(job)

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    test_factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)

    with patch("app.db.session.get_session_factory", return_value=test_factory):
        await _execute_job(job)

    await db.refresh(job)
    assert job.status == "dead"
    assert "No handler" in (job.last_error or "")


@pytest.mark.asyncio
async def test_execute_job_failure_retries(db):
    """Failed job retries with backoff until max_retries, then moves to dead."""
    from app.services.job_queue import _execute_job, _handlers, enqueue

    async def failing_handler(**kwargs):
        raise ValueError("intentional failure")

    _handlers["test_fail"] = failing_handler
    try:
        job_id = await enqueue("test_fail", {}, db=db, max_retries=2)
        await db.commit()

        job = await db.get(JobEntry, job_id)
        job.status = "running"
        job.attempts = 1
        await db.commit()
        await db.refresh(job)

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        test_factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)

        # First failure: should retry (attempts=1, max=2)
        with patch("app.db.session.get_session_factory", return_value=test_factory):
            await _execute_job(job)

        await db.refresh(job)
        assert job.status == "pending"
        assert "intentional failure" in (job.last_error or "")

        # Second failure: should be dead (attempts=2, max=2)
        job.status = "running"
        job.attempts = 2
        await db.commit()
        await db.refresh(job)

        with patch("app.db.session.get_session_factory", return_value=test_factory):
            await _execute_job(job)

        await db.refresh(job)
        assert job.status == "dead"
    finally:
        _handlers.pop("test_fail", None)


# ── Queue Stats ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_queue_stats(db):
    from app.services.job_queue import enqueue, get_queue_stats

    await enqueue("stat_test_1", {}, db=db)
    await enqueue("stat_test_2", {}, db=db)
    await db.commit()

    stats = await get_queue_stats(db, organization_id=1)
    assert stats["total"] >= 2
    assert stats["pending"] >= 2
    assert "worker_id" in stats
    assert isinstance(stats["worker_running"], bool)


# ── Sentry Config ────────────────────────────────────────────────────────────

def test_sentry_config_defaults():
    from app.core.config import settings

    assert settings.SENTRY_DSN == "" or isinstance(settings.SENTRY_DSN, str)
    assert 0.0 <= settings.SENTRY_TRACES_SAMPLE_RATE <= 1.0
    assert isinstance(settings.SENTRY_ENVIRONMENT, str)


# ── Job Queue Config ─────────────────────────────────────────────────────────

def test_job_queue_config_defaults():
    from app.core.config import settings

    assert isinstance(settings.JOB_QUEUE_ENABLED, bool)
    assert settings.JOB_QUEUE_POLL_SECONDS > 0
    assert settings.JOB_QUEUE_MAX_WORKERS > 0
    assert settings.JOB_QUEUE_MAX_RETRIES > 0
    assert settings.JOB_QUEUE_RETRY_BACKOFF_SECONDS > 0
    assert settings.JOB_QUEUE_STALE_TIMEOUT_SECONDS > 0


# ── Job Handlers Registration ────────────────────────────────────────────────

def test_job_handlers_registered():
    """Verify that importing job_handlers registers the expected handlers."""
    import app.jobs.job_handlers  # noqa: F401
    from app.services.job_queue import _handlers

    assert "embed_memory" in _handlers
    assert "backfill_embeddings" in _handlers
    assert "batch_score_contacts" in _handlers


# ── Enqueue Sync ─────────────────────────────────────────────────────────────

def test_enqueue_sync_no_loop():
    """enqueue_sync should not crash when there's no event loop."""
    from app.services.job_queue import enqueue_sync
    # This should be a no-op, not raise
    enqueue_sync("test_no_loop", {"x": 1})
