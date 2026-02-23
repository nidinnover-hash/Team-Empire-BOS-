from __future__ import annotations

import json
import time
from typing import Any, cast

_TTL_SECONDS = 60 * 30
_MAX_ITEMS = 5_000
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_key(scope: str, key: str) -> str:
    return f"{scope}:{key}"


def _cleanup(now: float) -> None:
    stale = [k for k, (ts, _payload) in _cache.items() if now - ts > _TTL_SECONDS]
    for k in stale:
        _cache.pop(k, None)
    if len(_cache) > _MAX_ITEMS:
        # Drop oldest entries to keep in-memory cache bounded.
        oldest = sorted(_cache.items(), key=lambda item: item[1][0])[: len(_cache) - _MAX_ITEMS]
        for k, _ in oldest:
            _cache.pop(k, None)


def get_cached_response(scope: str, key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    _cleanup(now)
    hit = _cache.get(_cache_key(scope, key))
    if not hit:
        return None
    _ts, payload = hit
    # Return a detached copy so callers cannot mutate cached state.
    return cast(dict[str, Any], json.loads(json.dumps(payload)))


def store_response(scope: str, key: str, payload: dict[str, Any]) -> None:
    now = time.monotonic()
    _cleanup(now)
    # Keep payload JSON-serializable and detached from caller mutation.
    _cache[_cache_key(scope, key)] = (now, json.loads(json.dumps(payload)))
