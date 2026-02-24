"""
Middleware stack:
- SecurityHeadersMiddleware: adds security and contract headers.
- CorrelationIDMiddleware: per-request correlation IDs.
- RequestLogMiddleware: structured request logging with context.
- RateLimitMiddleware: in-memory/Redis sliding window throttling.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
import logging
from importlib import import_module
from threading import Lock
from urllib.parse import parse_qsl, urlencode
from typing import Protocol, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.contracts import API_CONTRACT_VERSION
from app.core.request_context import reset_current_request_id, set_current_request_id
from app.core.security import decode_access_token

logger = logging.getLogger("request")
_rate_limit_stats: dict[str, int] = {
    "allowed": 0,
    "blocked": 0,
    "fallback_to_memory": 0,
}


def get_rate_limit_stats() -> dict[str, int]:
    return dict(_rate_limit_stats)

_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "client_secret",
    "code",
    "hub.verify_token",
    "id_token",
    "password",
    "refresh_token",
    "secret",
    "signature",
    "sig",
    "state",
    "token",
}


def sanitize_query_for_logs(query: str) -> str:
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    safe_pairs: list[tuple[str, str]] = []
    for key, value in pairs:
        key_lower = key.lower()
        if (
            key_lower in _SENSITIVE_QUERY_KEYS
            or "token" in key_lower
            or "secret" in key_lower
            or "password" in key_lower
        ):
            safe_pairs.append((key, "[REDACTED]"))
        else:
            safe_pairs.append((key, value))
    return urlencode(safe_pairs)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard HTTP security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = cast(Response, await call_next(request))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["X-API-Contract-Version"] = API_CONTRACT_VERSION
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        # Strict-Transport-Security only when served over HTTPS
        if settings.COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        token = set_current_request_id(correlation_id)
        try:
            response = cast(Response, await call_next(request))
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            reset_current_request_id(token)


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per request with correlation context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response: Response | None = None
        status_code = 500
        try:
            response = cast(Response, await call_next(request))
            status_code = response.status_code
            return response
        finally:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            request_id = getattr(request.state, "correlation_id", None)
            org_id = None
            user_id = None
            auth_header = request.headers.get("Authorization", "")
            token = None
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()
            if not token:
                token = request.cookies.get("pc_session")
            if token:
                try:
                    claims = decode_access_token(token)
                    org_id = claims.get("org_id")
                    user_id = claims.get("id")
                except Exception:
                    pass
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query": sanitize_query_for_logs(request.url.query),
                    "status_code": status_code,
                    "latency_ms": elapsed_ms,
                    "org_id": org_id,
                    "user_id": user_id,
                    "client_ip": request.client.host if request.client else None,
                },
            )


# -- Rate Limiter --------------------------------------------------------------
# In-memory sliding window per client IP. Resets on server restart (by design
# for a personal tool; use Redis for multi-instance deployments).

_rate_buckets: dict[str, deque] = defaultdict(deque)
_rate_limit_lock = Lock()

# Paths exempt from rate limiting (health checks, docs)
_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/web/", "/static/")

# -- Login Failure Tracker -----------------------------------------------------
# Sliding window per IP; resets on server restart (acceptable for a personal tool).

_login_failures: dict[str, deque] = defaultdict(deque)
LOGIN_FAIL_WINDOW = 900   # 15-minute window
LOGIN_FAIL_MAX = 10       # max failures before lockout
_LOGIN_MAX_IPS = 10_000   # cap to prevent memory leak from IP churn
_login_lock = Lock()

_redis_client: _RedisLike | None = None
_redis_initialized = False


class _RedisLike(Protocol):
    def zremrangebyscore(self, key: str, min: int | float | str, max: int | float | str) -> int: ...
    def zcard(self, key: str) -> int: ...
    def zadd(self, key: str, mapping: dict[str, int]) -> int: ...
    def expire(self, key: str, seconds: int) -> bool: ...
    def delete(self, key: str) -> int: ...
    def ping(self) -> bool: ...


def _resolve_rate_limit_redis_url() -> str:
    primary = (settings.RATE_LIMIT_REDIS_URL or "").strip()
    if primary:
        return primary
    # Backward-compatible fallback: reuse idempotency Redis if configured.
    return (settings.IDEMPOTENCY_REDIS_URL or "").strip()


def _get_redis_client() -> _RedisLike | None:
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client
    _redis_initialized = True
    redis_url = _resolve_rate_limit_redis_url()
    if not redis_url:
        return None
    try:
        redis_module = import_module("redis")
        client = cast(
            _RedisLike,
            redis_module.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=0.25,
                socket_connect_timeout=0.25,
            ),
        )
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception:
        logger.warning("Redis unavailable for rate limiting; using in-memory fallback.", exc_info=True)
        return None


def _rate_backend() -> str:
    backend = settings.RATE_LIMIT_BACKEND
    if backend == "memory":
        return "memory"
    if backend == "redis":
        return "redis" if _get_redis_client() is not None else "memory"
    return "redis" if _get_redis_client() is not None else "memory"


def _rate_key(client_ip: str) -> str:
    prefix = (settings.RATE_LIMIT_REDIS_PREFIX or "pc:ratelimit").strip() or "pc:ratelimit"
    return f"{prefix}:request:{client_ip}"


def _login_key(client_ip: str) -> str:
    prefix = (settings.RATE_LIMIT_REDIS_PREFIX or "pc:ratelimit").strip() or "pc:ratelimit"
    return f"{prefix}:login:{client_ip}"


def _mark_and_count_redis(key: str, window_seconds: int, add_event: bool) -> int | None:
    client = _get_redis_client()
    if client is None:
        return None
    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    min_score = now_ms - window_ms
    member = f"{now_ms}:{uuid.uuid4().hex}"
    try:
        client.zremrangebyscore(key, 0, min_score)
        if add_event:
            client.zadd(key, {member: now_ms})
            client.expire(key, window_seconds + 10)
        return int(client.zcard(key))
    except Exception:
        logger.warning("Redis rate-limit operation failed; using in-memory fallback.", exc_info=True)
        _rate_limit_stats["fallback_to_memory"] += 1
        return None


def check_login_allowed(ip: str) -> bool:
    """Return True if the IP is below the failed-login threshold."""
    if _rate_backend() == "redis":
        count = _mark_and_count_redis(_login_key(ip), LOGIN_FAIL_WINDOW, add_event=False)
        if count is not None:
            return count < LOGIN_FAIL_MAX
    now = time.monotonic()
    with _login_lock:
        bucket = _login_failures[ip]
        while bucket and now - bucket[0] > LOGIN_FAIL_WINDOW:
            bucket.popleft()
        return len(bucket) < LOGIN_FAIL_MAX


def record_login_failure(ip: str) -> None:
    """Record one failed login attempt for this IP."""
    if _rate_backend() == "redis":
        count = _mark_and_count_redis(_login_key(ip), LOGIN_FAIL_WINDOW, add_event=True)
        if count is not None:
            return
    now = time.monotonic()
    with _login_lock:
        # Evict stale IPs if dict exceeds cap to prevent memory leak
        if len(_login_failures) >= _LOGIN_MAX_IPS:
            stale = [
                k for k, v in _login_failures.items()
                if not v or now - v[-1] > LOGIN_FAIL_WINDOW
            ]
            for k in stale:
                del _login_failures[k]
        _login_failures[ip].append(now)


def clear_login_failures(ip: str) -> None:
    """Clear failed-login history for this IP after successful authentication."""
    if _rate_backend() == "redis":
        client = _get_redis_client()
        if client is not None:
            try:
                client.delete(_login_key(ip))
            except Exception:
                logger.warning("Redis login-failure clear failed; clearing memory fallback.", exc_info=True)
    with _login_lock:
        _login_failures.pop(ip, None)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return cast(Response, await call_next(request))

        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return cast(Response, await call_next(request))

        client_ip = request.client.host if request.client else "unknown"
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        max_req = settings.RATE_LIMIT_MAX_REQUESTS
        if _rate_backend() == "redis":
            count = _mark_and_count_redis(_rate_key(client_ip), window, add_event=False)
            if count is not None:
                if count >= max_req:
                    _rate_limit_stats["blocked"] += 1
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                f"Rate limit exceeded: {max_req} requests per "
                                f"{window}s. Please slow down."
                            )
                        },
                        headers={"Retry-After": str(window)},
                    )
                _ = _mark_and_count_redis(_rate_key(client_ip), window, add_event=True)
                _rate_limit_stats["allowed"] += 1
                return cast(Response, await call_next(request))

        now = time.monotonic()
        acquired = _rate_limit_lock.acquire(timeout=1.0)
        if not acquired:
            # Lock contention — let the request through rather than deadlock
            return cast(Response, await call_next(request))
        try:
            bucket = _rate_buckets[client_ip]
            # Drop timestamps outside the sliding window
            while bucket and now - bucket[0] > window:
                bucket.popleft()

            if len(bucket) >= max_req:
                _rate_limit_stats["blocked"] += 1
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Rate limit exceeded: {max_req} requests per "
                            f"{window}s. Please slow down."
                        )
                    },
                    headers={"Retry-After": str(window)},
                )

            bucket.append(now)
            remaining = max_req - len(bucket)
            _rate_limit_stats["allowed"] += 1
        finally:
            _rate_limit_lock.release()
        response = cast(Response, await call_next(request))
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(window)
        return response
