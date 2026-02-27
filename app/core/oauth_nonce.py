from __future__ import annotations

import logging
from importlib import import_module
from threading import Lock
from time import time
from typing import Protocol

from app.core.config import settings

_used_nonces: dict[str, float] = {}
_nonce_lock = Lock()
_redis_client: _RedisLike | None = None
_redis_initialized = False
_MAX_NONCE_ITEMS = 10_000  # Cap to prevent memory leak from nonce churn
logger = logging.getLogger(__name__)


class _RedisLike(Protocol):
    def set(self, name: str, value: str, ex: int, nx: bool) -> object: ...


def _redis_url() -> str:
    primary = (settings.RATE_LIMIT_REDIS_URL or "").strip()
    if primary:
        return primary
    fallback = (settings.IDEMPOTENCY_REDIS_URL or "").strip()
    return fallback


def _get_redis_client() -> _RedisLike | None:
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client
    _redis_initialized = True
    url = _redis_url()
    if not url:
        return None
    try:
        redis_module = import_module("redis")
        _redis_client = redis_module.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=0.25,
            socket_connect_timeout=0.25,
        )
    except (ImportError, ModuleNotFoundError, AttributeError, TypeError, ValueError):
        _redis_client = None
    return _redis_client


def consume_oauth_nonce_once(namespace: str, nonce: str, *, max_age_seconds: int) -> bool:
    """
    Return True only the first time a nonce is seen within the replay window.
    Later calls with the same nonce return False until the window expires.
    """
    ttl = max(max_age_seconds, 1)
    now = time()
    key = f"{namespace}:{nonce}"
    redis_client = _get_redis_client()
    if redis_client is None and not settings.DEBUG:
        logger.error("OAuth nonce protection requires Redis when DEBUG=false")
        return False
    if redis_client is not None:
        try:
            created = redis_client.set(name=key, value="1", ex=ttl, nx=True)
            return bool(created)
        except (RuntimeError, OSError, TypeError, ValueError) as exc:
            # Fall back to in-memory replay protection when Redis is unavailable.
            logger.warning("OAuth nonce Redis fallback engaged: %s", type(exc).__name__)

    expiry = now + ttl
    with _nonce_lock:
        # Evict expired nonces
        for seen_key, seen_expiry in list(_used_nonces.items()):
            if seen_expiry <= now:
                _used_nonces.pop(seen_key, None)
        # Cap total size to prevent unbounded growth
        if len(_used_nonces) >= _MAX_NONCE_ITEMS:
            oldest = sorted(_used_nonces.items(), key=lambda item: item[1])[:len(_used_nonces) - _MAX_NONCE_ITEMS + 1]
            for k, _ in oldest:
                _used_nonces.pop(k, None)
        if key in _used_nonces:
            return False
        _used_nonces[key] = expiry
        return True
