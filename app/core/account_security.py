"""Account security hardening — per-account lockout, session registry, idle timeout.

Supplements the existing per-IP rate limiting with per-account protections:
- Exponential lockout after repeated failed logins
- Concurrent session limiting (oldest session evicted)
- Idle session timeout tracking
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Per-account lockout ─────────────────────────────────────────────────────


def _lockout_durations() -> list[int]:
    from app.core.config import settings
    raw = settings.ACCOUNT_LOCKOUT_DURATIONS_MINUTES
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return [1, 5, 15, 60]


def _lockout_threshold() -> int:
    from app.core.config import settings
    return settings.ACCOUNT_LOCKOUT_THRESHOLD


def compute_lockout_until(failed_count: int) -> datetime | None:
    """Return the lockout expiry time, or None if below threshold."""
    threshold = _lockout_threshold()
    if failed_count < threshold:
        return None
    durations = _lockout_durations()
    tier = min((failed_count - threshold) // threshold, len(durations) - 1)
    minutes = durations[tier]
    return datetime.now(UTC) + timedelta(minutes=minutes)


async def check_account_locked(db: AsyncSession, user: Any) -> bool:
    """Return True if the user account is currently locked."""
    locked_until = getattr(user, "locked_until", None)
    if locked_until is None:
        return False
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    if datetime.now(UTC) < locked_until:
        return True
    # Lock expired — clear it
    user.locked_until = None
    user.failed_login_count = 0
    db.add(user)
    await db.flush()
    return False


async def record_account_login_failure(db: AsyncSession, user: Any) -> None:
    """Increment failure counter and set lockout if threshold exceeded."""
    current = getattr(user, "failed_login_count", 0) or 0
    new_count = current + 1
    user.failed_login_count = new_count
    user.locked_until = compute_lockout_until(new_count)
    db.add(user)
    await db.flush()
    if user.locked_until:
        logger.warning(
            "Account %d locked until %s after %d failures",
            user.id, user.locked_until.isoformat(), new_count,
        )


async def reset_account_login_failures(db: AsyncSession, user: Any) -> None:
    """Clear failure counter and lockout on successful login."""
    if getattr(user, "failed_login_count", 0) or getattr(user, "locked_until", None):
        user.failed_login_count = 0
        user.locked_until = None
        db.add(user)
        await db.flush()


async def unlock_account(db: AsyncSession, user: Any) -> None:
    """Admin-initiated account unlock."""
    user.failed_login_count = 0
    user.locked_until = None
    db.add(user)
    await db.flush()


# ── Session registry (in-memory) ────────────────────────────────────────────

_active_sessions: dict[int, list[dict[str, Any]]] = {}
_session_lock = asyncio.Lock()


def _max_sessions() -> int:
    from app.core.config import settings
    return settings.ACCOUNT_MAX_CONCURRENT_SESSIONS


def _idle_timeout_seconds() -> int:
    from app.core.config import settings
    return settings.ACCOUNT_IDLE_TIMEOUT_MINUTES * 60


async def register_session(user_id: int, session_id: str) -> str | None:
    """Register a new session. Returns evicted session_id if limit exceeded."""
    async with _session_lock:
        _active_sessions.setdefault(user_id, [])

        # Purge expired idle sessions first
        _purge_idle(user_id)

        sessions = _active_sessions[user_id]
        max_s = _max_sessions()

        evicted_id: str | None = None
        if len(sessions) >= max_s:
            evicted = sessions.pop(0)  # oldest
            evicted_id = evicted["session_id"]
            logger.info("Evicted oldest session %s for user %d (limit %d)", evicted_id, user_id, max_s)

        sessions.append({
            "session_id": session_id,
            "created_at": time.monotonic(),
            "last_activity": time.monotonic(),
        })

        return evicted_id


async def touch_session(user_id: int, session_id: str) -> None:
    """Update last_activity for idle timeout tracking."""
    async with _session_lock:
        sessions = _active_sessions.get(user_id, [])
        for s in sessions:
            if s["session_id"] == session_id:
                s["last_activity"] = time.monotonic()
                return


async def is_session_valid(user_id: int, session_id: str) -> bool:
    """Check if session exists and is not idle-expired."""
    async with _session_lock:
        sessions = _active_sessions.get(user_id, [])
        timeout = _idle_timeout_seconds()
        now = time.monotonic()
        for s in sessions:
            if s["session_id"] == session_id:
                return not (now - s["last_activity"]) > timeout
        return False


async def remove_session(user_id: int, session_id: str) -> None:
    """Remove session on logout."""
    async with _session_lock:
        sessions = _active_sessions.get(user_id, [])
        _active_sessions[user_id] = [s for s in sessions if s["session_id"] != session_id]


async def active_session_count(user_id: int) -> int:
    """Return number of active sessions for a user."""
    async with _session_lock:
        _purge_idle(user_id)
        return len(_active_sessions.get(user_id, []))


async def clear_all_sessions(user_id: int) -> None:
    """Clear all sessions for a user (used on password change / force logout)."""
    async with _session_lock:
        _active_sessions.pop(user_id, None)


def _purge_idle(user_id: int) -> None:
    """Remove idle-expired sessions."""
    sessions = _active_sessions.get(user_id, [])
    if not sessions:
        return
    timeout = _idle_timeout_seconds()
    now = time.monotonic()
    _active_sessions[user_id] = [s for s in sessions if (now - s["last_activity"]) <= timeout]


def _reset_registry() -> None:
    """Reset session registry — for testing only."""
    _active_sessions.clear()
