"""Persistent job queue — Postgres-backed async task queue with retry and backoff.

Usage:
    from app.services.job_queue import enqueue
    await enqueue("send_email", {"to": "a@b.com", "subject": "Hi"})

    # Or fire-and-forget from sync context:
    from app.services.job_queue import enqueue_sync
    enqueue_sync("embed_memory", {"org_id": 1, "source_type": "profile_memory", ...})

Jobs are processed by a background worker that polls the job_queue table.
Failed jobs retry with exponential backoff up to max_retries, then move to 'dead' status.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import platform
import traceback
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.job_queue import JobEntry

logger = logging.getLogger(__name__)

# ── Job Registry ─────────────────────────────────────────────────────────────
# Map job_name → async handler function
_handlers: dict[str, Callable[..., Awaitable[None]]] = {}
_worker_task: asyncio.Task[None] | None = None
_worker_stop_event: asyncio.Event | None = None
_worker_id: str = f"{platform.node()}-{id(object()):x}"
_background_tasks: set[asyncio.Task[object]] = set()


def register_handler(job_name: str, handler: Callable[..., Awaitable[None]]) -> None:
    """Register an async handler for a job type."""
    _handlers[job_name] = handler


def handler(job_name: str):
    """Decorator to register a job handler."""
    def decorator(fn: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        register_handler(job_name, fn)
        return fn
    return decorator


# ── Enqueue ──────────────────────────────────────────────────────────────────

async def enqueue(
    job_name: str,
    payload: dict | None = None,
    *,
    db: AsyncSession | None = None,
    priority: int = 0,
    delay_seconds: int = 0,
    max_retries: int | None = None,
) -> int:
    """Enqueue a job for async processing. Returns the job ID."""
    run_after = datetime.now(UTC)
    if delay_seconds > 0:
        run_after += timedelta(seconds=delay_seconds)

    entry = JobEntry(
        job_name=job_name,
        payload_json=json.dumps(payload or {}),
        status="pending",
        priority=priority,
        max_retries=max_retries if max_retries is not None else settings.JOB_QUEUE_MAX_RETRIES,
        run_after=run_after,
    )

    if db is not None:
        db.add(entry)
        await db.flush()
        return entry.id

    # Open a new session if none provided
    from app.db.session import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry.id


def enqueue_sync(
    job_name: str,
    payload: dict | None = None,
    *,
    priority: int = 0,
    delay_seconds: int = 0,
    max_retries: int | None = None,
) -> None:
    """Fire-and-forget enqueue from sync context. Schedules via asyncio task."""
    if not settings.JOB_QUEUE_ENABLED:
        return
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(enqueue(
            job_name, payload,
            priority=priority,
            delay_seconds=delay_seconds,
            max_retries=max_retries,
        ))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        logger.debug("No running event loop; skipping job enqueue for %s", job_name)


# ── Worker ───────────────────────────────────────────────────────────────────

async def _claim_job(db: AsyncSession) -> JobEntry | None:
    """Atomically claim the next pending job using SELECT ... FOR UPDATE SKIP LOCKED."""
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(seconds=settings.JOB_QUEUE_STALE_TIMEOUT_SECONDS)

    # First, recover stale running jobs (worker crashed)
    await db.execute(
        update(JobEntry)
        .where(
            JobEntry.status == "running",
            JobEntry.locked_at < stale_cutoff,
        )
        .values(status="pending", locked_at=None, locked_by=None)
    )

    # pgvector-safe: use raw SQL for FOR UPDATE SKIP LOCKED since SQLAlchemy
    # ORM .with_for_update(skip_locked=True) works fine with asyncpg
    stmt = (
        select(JobEntry)
        .where(
            JobEntry.status == "pending",
            JobEntry.run_after <= now,
        )
        .order_by(JobEntry.priority.desc(), JobEntry.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        return None

    job.status = "running"
    job.locked_at = now
    job.locked_by = _worker_id
    job.attempts += 1
    await db.commit()
    await db.refresh(job)
    return job


async def _execute_job(job: JobEntry) -> None:
    """Execute a single job and update its status."""
    from app.db.session import get_session_factory
    factory = get_session_factory()

    handler_fn = _handlers.get(job.job_name)
    if handler_fn is None:
        logger.error("No handler registered for job %r (id=%d)", job.job_name, job.id)
        async with factory() as db:
            job_row = await db.get(JobEntry, job.id)
            if job_row:
                job_row.status = "dead"
                job_row.last_error = f"No handler registered for {job.job_name!r}"
                job_row.completed_at = datetime.now(UTC)
                await db.commit()
        return

    try:
        payload = json.loads(job.payload_json)
        await handler_fn(**payload)
    except Exception as exc:
        tb = traceback.format_exc()
        logger.warning(
            "Job %s (id=%d) failed attempt %d/%d: %s",
            job.job_name, job.id, job.attempts, job.max_retries, exc,
        )
        async with factory() as db:
            job_row = await db.get(JobEntry, job.id)
            if not job_row:
                return
            job_row.last_error = f"{exc.__class__.__name__}: {exc}\n{tb[-500:]}"
            if job_row.attempts >= job_row.max_retries:
                job_row.status = "dead"
                job_row.completed_at = datetime.now(UTC)
                logger.error("Job %s (id=%d) exhausted retries, moved to dead", job.job_name, job.id)
            else:
                # Exponential backoff: base * 2^(attempt-1)
                backoff = settings.JOB_QUEUE_RETRY_BACKOFF_SECONDS * (2 ** (job_row.attempts - 1))
                job_row.status = "pending"
                job_row.run_after = datetime.now(UTC) + timedelta(seconds=backoff)
                job_row.locked_at = None
                job_row.locked_by = None
            await db.commit()
        return

    # Success
    async with factory() as db:
        job_row = await db.get(JobEntry, job.id)
        if job_row:
            job_row.status = "completed"
            job_row.completed_at = datetime.now(UTC)
            job_row.locked_at = None
            job_row.locked_by = None
            await db.commit()


async def _worker_loop() -> None:
    """Main worker loop — polls for jobs and executes them."""
    from app.db.session import get_session_factory
    factory = get_session_factory()
    poll_interval = settings.JOB_QUEUE_POLL_SECONDS

    logger.info("Job queue worker started (id=%s, poll=%ds)", _worker_id, poll_interval)

    while not _worker_stop_event.is_set():
        try:
            async with factory() as db:
                job = await _claim_job(db)

            if job is not None:
                await _execute_job(job)
                continue  # Check for more jobs immediately
        except Exception:
            logger.warning("Job queue worker error", exc_info=True)

        # No job found or error — wait before polling again
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                _worker_stop_event.wait(),
                timeout=poll_interval,
            )

    logger.info("Job queue worker stopped (id=%s)", _worker_id)


def start_worker() -> None:
    """Start the background job queue worker."""
    global _worker_task, _worker_stop_event

    if not settings.JOB_QUEUE_ENABLED:
        return

    # Skip on SQLite (tests)
    db_url = (settings.DATABASE_URL or "").strip().lower()
    if db_url.startswith("sqlite"):
        return

    _worker_stop_event = asyncio.Event()
    try:
        loop = asyncio.get_running_loop()
        _worker_task = loop.create_task(_worker_loop())
    except RuntimeError:
        logger.debug("No running event loop; skipping job queue worker start")


async def stop_worker() -> None:
    """Gracefully stop the job queue worker."""
    global _worker_task, _worker_stop_event

    if _worker_stop_event is not None:
        _worker_stop_event.set()

    if _worker_task is not None and not _worker_task.done():
        try:
            await asyncio.wait_for(_worker_task, timeout=settings.SHUTDOWN_GRACE_SECONDS)
        except TimeoutError:
            _worker_task.cancel()
        _worker_task = None


# ── Stats ────────────────────────────────────────────────────────────────────

async def get_queue_stats(db: AsyncSession, *, organization_id: int) -> dict:
    """Return job queue statistics."""
    from sqlalchemy import case, func
    result = await db.execute(
        select(
            func.count(JobEntry.id).label("total"),
            func.count(case((JobEntry.status == "pending", 1))).label("pending"),
            func.count(case((JobEntry.status == "running", 1))).label("running"),
            func.count(case((JobEntry.status == "completed", 1))).label("completed"),
            func.count(case((JobEntry.status == "failed", 1))).label("failed"),
            func.count(case((JobEntry.status == "dead", 1))).label("dead"),
        )
    )
    row = result.one()
    return {
        "total": row.total,
        "pending": row.pending,
        "running": row.running,
        "completed": row.completed,
        "failed": row.failed,
        "dead": row.dead,
        "worker_id": _worker_id,
        "worker_running": _worker_task is not None and not _worker_task.done(),
    }
