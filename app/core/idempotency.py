from __future__ import annotations

import json
import logging
import time
from importlib import import_module
from threading import Lock
from typing import Any, Protocol, cast

from app.core.config import settings

logger = logging.getLogger(__name__)


class _RedisLike(Protocol):
    def get(self, key: str) -> str | bytes | None: ...
    def setex(self, key: str, time: int, value: str) -> object: ...


_IN_MEMORY_DEFAULT_TTL_SECONDS = 60 * 30
_IN_MEMORY_DEFAULT_MAX_ITEMS = 5_000
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = Lock()
_redis_client: _RedisLike | None = None
_redis_initialized = False


def _cache_key(scope: str, key: str) -> str:
    return f"{scope}:{key}"


def _redis_key(scope: str, key: str) -> str:
    prefix = (settings.IDEMPOTENCY_REDIS_PREFIX or "pc:idempotency").strip() or "pc:idempotency"
    return f"{prefix}:{scope}:{key}"


def _json_clone(payload: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(payload)))


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
    except Exception:
        logger.warning("Redis idempotency requested but redis package is not installed; using memory backend.")
        return None
    try:
        client = cast(
            _RedisLike,
            redis_module.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=0.25,
                socket_connect_timeout=0.25,
            ),
        )
        client.get("__idempotency_healthcheck__")
        _redis_client = client
        return _redis_client
    except Exception:
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


def get_cached_response(scope: str, key: str) -> dict[str, Any] | None:
    if _backend() == "redis":
        client = _get_redis_client()
        if client is not None:
            raw = client.get(_redis_key(scope, key))
            if raw:
                try:
                    payload = cast(dict[str, Any], json.loads(raw))
                    return _json_clone(payload)
                except Exception:
                    return None
    now = time.monotonic()
    with _cache_lock:
        _cleanup(now)
        hit = _cache.get(_cache_key(scope, key))
        if not hit:
            return None
        _ts, payload = hit
        return _json_clone(payload)


def store_response(scope: str, key: str, payload: dict[str, Any]) -> None:
    safe_payload = _json_clone(payload)
    if _backend() == "redis":
        client = _get_redis_client()
        if client is not None:
            try:
                client.setex(
                    _redis_key(scope, key),
                    _ttl_seconds(),
                    json.dumps(safe_payload),
                )
                return
            except Exception:
                logger.warning("Redis idempotency write failed; falling back to memory backend.", exc_info=True)
    now = time.monotonic()
    with _cache_lock:
        _cleanup(now)
        # Keep payload JSON-serializable and detached from caller mutation.
        _cache[_cache_key(scope, key)] = (now, safe_payload)
