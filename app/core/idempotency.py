from __future__ import annotations

import hashlib
import json
import logging
import time
from importlib import import_module
from threading import Lock
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


class _RedisLike(Protocol):
    def get(self, key: str) -> str | bytes | None: ...
    def setex(self, key: str, time: int, value: str) -> object: ...


class IdempotencyConflictError(ValueError):
    pass


_IN_MEMORY_DEFAULT_TTL_SECONDS = 60 * 30
_IN_MEMORY_DEFAULT_MAX_ITEMS = 5_000
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = Lock()
_redis_client: _RedisLike | None = None
_redis_initialized = False
_idempotency_stats: dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "stores": 0,
    "conflicts": 0,
    "redis_failures": 0,
}


def get_idempotency_stats() -> dict[str, int]:
    return dict(_idempotency_stats)


def _cache_key(scope: str, key: str) -> str:
    return f"{scope}:{key}"


def _redis_key(scope: str, key: str) -> str:
    prefix = (settings.IDEMPOTENCY_REDIS_PREFIX or "pc:idempotency").strip() or "pc:idempotency"
    return f"{prefix}:{scope}:{key}"


def _json_clone(payload: dict[str, Any]) -> dict[str, Any]:
    cloned = json.loads(json.dumps(payload))
    return cloned if isinstance(cloned, dict) else {}


def _json_loads_dict(raw: str | bytes) -> dict[str, Any] | None:
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else None


def build_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ttl_seconds() -> int:
    ttl = settings.IDEMPOTENCY_TTL_SECONDS
    return ttl if ttl >= 60 else _IN_MEMORY_DEFAULT_TTL_SECONDS


def _max_items() -> int:
    max_items = settings.IDEMPOTENCY_MAX_ITEMS
    return max_items if max_items >= 100 else _IN_MEMORY_DEFAULT_MAX_ITEMS


def _cleanup(now: float) -> None:
    ttl_seconds = _ttl_seconds()
    max_items = _max_items()
    stale = [k for k, (ts, _payload) in _cache.items() if now - ts > ttl_seconds]
    for k in stale:
        _cache.pop(k, None)
    if len(_cache) > max_items:
        # Drop oldest entries to keep in-memory cache bounded.
        oldest = sorted(_cache.items(), key=lambda item: item[1][0])[: len(_cache) - max_items]
        for k, _ in oldest:
            _cache.pop(k, None)


def _get_redis_client() -> _RedisLike | None:
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client
    _redis_initialized = True
    redis_url = (settings.IDEMPOTENCY_REDIS_URL or "").strip()
    if not redis_url:
        return None
    try:
        redis_module = import_module("redis")
    except (ImportError, ModuleNotFoundError):
        logger.warning("Redis idempotency requested but redis package is not installed; using memory backend.")
        return None
    try:
        client = redis_module.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=0.25,
            socket_connect_timeout=0.25,
        )
        client.get("__idempotency_healthcheck__")
        _redis_client = client
        return _redis_client
    except (RuntimeError, OSError, TypeError, ValueError):
        logger.warning("Redis idempotency unavailable; using memory backend.", exc_info=True)
        return None


def _backend() -> str:
    backend = (settings.IDEMPOTENCY_BACKEND or "auto").strip().lower()
    if backend == "memory":
        return "memory"
    if backend == "redis":
        return "redis" if _get_redis_client() is not None else "memory"
    if backend == "auto":
        return "redis" if _get_redis_client() is not None else "memory"
    return "memory"


def _unpack_cached(raw: dict[str, Any], fingerprint: str | None) -> dict[str, Any]:
    stored_fingerprint = raw.get("fingerprint")
    if isinstance(stored_fingerprint, str) and fingerprint and stored_fingerprint != fingerprint:
        _idempotency_stats["conflicts"] += 1
        raise IdempotencyConflictError("Idempotency key replayed with different request fingerprint")
    payload = raw.get("payload")
    if isinstance(payload, dict):
        return _json_clone(payload)
    # Backward compatibility with legacy entries that store payload directly.
    return _json_clone(raw)


def get_cached_response(scope: str, key: str, fingerprint: str | None = None) -> dict[str, Any] | None:
    if _backend() == "redis":
        client = _get_redis_client()
        if client is not None:
            raw = client.get(_redis_key(scope, key))
            if raw:
                try:
                    payload = _json_loads_dict(raw)
                    if payload is None:
                        raise ValueError("Invalid idempotency payload type")
                    _idempotency_stats["hits"] += 1
                    return _unpack_cached(payload, fingerprint)
                except IdempotencyConflictError:
                    raise
                except (TypeError, ValueError, json.JSONDecodeError):
                    logger.debug("Idempotency cache parse failed for %s", key, exc_info=True)
                    _idempotency_stats["redis_failures"] += 1
                    return None
            _idempotency_stats["misses"] += 1
            return None
    now = time.monotonic()
    with _cache_lock:
        _cleanup(now)
        hit = _cache.get(_cache_key(scope, key))
        if not hit:
            _idempotency_stats["misses"] += 1
            return None
        _ts, payload = hit
        _idempotency_stats["hits"] += 1
        return _unpack_cached(payload, fingerprint)


def store_response(
    scope: str,
    key: str,
    payload: dict[str, Any],
    fingerprint: str | None = None,
) -> None:
    safe_payload = _json_clone(payload)
    cache_payload: dict[str, Any] = {"payload": safe_payload, "fingerprint": fingerprint}
    if _backend() == "redis":
        client = _get_redis_client()
        if client is not None:
            try:
                # Check for fingerprint collision before overwriting.
                if fingerprint:
                    existing = client.get(_redis_key(scope, key))
                    if existing:
                        try:
                            old = _json_loads_dict(existing)
                            if old is None:
                                raise ValueError("Invalid idempotency payload type")
                            old_fp = old.get("fingerprint")
                            if isinstance(old_fp, str) and old_fp != fingerprint:
                                _idempotency_stats["conflicts"] += 1
                                raise IdempotencyConflictError(
                                    "Idempotency key replayed with different request fingerprint"
                                )
                        except IdempotencyConflictError:
                            raise
                        except (TypeError, ValueError, json.JSONDecodeError):
                            logger.debug("Malformed idempotency entry for %s — overwriting", key, exc_info=True)
                client.setex(
                    _redis_key(scope, key),
                    _ttl_seconds(),
                    json.dumps(cache_payload),
                )
                _idempotency_stats["stores"] += 1
                return
            except IdempotencyConflictError:
                raise
            except (RuntimeError, OSError, TypeError, ValueError):
                logger.warning("Redis idempotency write failed; falling back to memory backend.", exc_info=True)
                _idempotency_stats["redis_failures"] += 1
    now = time.monotonic()
    with _cache_lock:
        _cleanup(now)
        # Check for fingerprint collision before overwriting in-memory entry.
        ck = _cache_key(scope, key)
        existing_entry = _cache.get(ck)
        if existing_entry and fingerprint:
            _ts, old_payload = existing_entry
            old_fp = old_payload.get("fingerprint")
            if isinstance(old_fp, str) and old_fp != fingerprint:
                _idempotency_stats["conflicts"] += 1
                raise IdempotencyConflictError(
                    "Idempotency key replayed with different request fingerprint"
                )
        _cache[ck] = (now, cache_payload)
    _idempotency_stats["stores"] += 1
