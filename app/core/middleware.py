"""
Middleware stack:
- SecurityHeadersMiddleware: adds security and contract headers.
- CorrelationIDMiddleware: per-request correlation IDs.
- RequestLogMiddleware: structured request logging with context.
- RequestBodyLimitMiddleware: rejects oversized request bodies.
- RateLimitMiddleware: in-memory/Redis sliding window throttling.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
import uuid
from collections import defaultdict, deque
from importlib import import_module
from threading import Lock
from typing import Protocol, cast
from urllib.parse import parse_qsl, urlencode

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.contracts import API_CONTRACT_VERSION
from app.core.request_context import reset_current_request_id, set_current_request_id
from app.core.security import decode_access_token

logger = logging.getLogger("request")
_LUCIDE_CDN_SOURCE = "https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js"
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
    "redirect_uri",
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
        import secrets
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = cast(Response, await call_next(request))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cache-Control"] = "no-store, must-revalidate, max-age=0"
        response.headers["X-API-Contract-Version"] = API_CONTRACT_VERSION
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' {_LUCIDE_CDN_SOURCE}; "
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
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.state.correlation_id = correlation_id
        token = set_current_request_id(correlation_id)
        try:
            response = cast(Response, await call_next(request))
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Request-ID"] = correlation_id
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
                except ValueError as exc:
                    logger.debug("Failed to decode token for request log context: %s", type(exc).__name__)
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
                    "client_ip": get_client_ip(request),
                },
            )


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds MAX_REQUEST_BODY_BYTES."""

    async def dispatch(self, request: Request, call_next) -> Response:
        max_bytes = settings.MAX_REQUEST_BODY_BYTES
        if max_bytes and request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    content_length_value = int(content_length)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Invalid Content-Length header."},
                    )
                if content_length_value > max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request body too large. Max {max_bytes // (1024 * 1024)} MB."
                        },
                    )
        return cast(Response, await call_next(request))


# -- Rate Limiter --------------------------------------------------------------
# In-memory sliding window per client IP. Resets on server restart (by design
# for a personal tool; use Redis for multi-instance deployments).

_rate_buckets: dict[str, deque] = defaultdict(deque)
_rate_limit_lock = asyncio.Lock()

# Paths exempt from rate limiting (health checks, docs)
_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/static/")

# -- Login Failure Tracker -----------------------------------------------------
# Sliding window per IP; resets on server restart (acceptable for a personal tool).

_login_failures: dict[str, deque] = defaultdict(deque)
LOGIN_FAIL_WINDOW = settings.LOGIN_FAIL_WINDOW_SECONDS
LOGIN_FAIL_MAX = settings.LOGIN_FAIL_MAX_ATTEMPTS
_LOGIN_MAX_IPS = 10_000   # cap to prevent memory leak from IP churn
_login_lock = Lock()

_redis_client: _RedisLike | None = None
_redis_initialized = False


def _trusted_proxy_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    raw = (settings.TRUSTED_PROXY_CIDRS or "").strip()
    if not raw:
        return []
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in raw.split(","):
        cidr = value.strip()
        if not cidr:
            continue
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            networks.append(network)
        except ValueError:
            logger.warning("Invalid TRUSTED_PROXY_CIDRS entry ignored: %r", cidr)
    return networks


def get_client_ip(request: Request) -> str:
    """
    Resolve client IP with optional trusted-proxy support.
    Trust X-Forwarded-For only when the direct peer is in TRUSTED_PROXY_CIDRS.
    """
    direct_ip = request.client.host if request.client else "unknown"
    if not settings.USE_FORWARDED_HEADERS:
        return direct_ip
    networks = _trusted_proxy_networks()
    if not networks:
        return direct_ip
    try:
        remote = ipaddress.ip_address(direct_ip)
    except ValueError:
        return direct_ip
    if not any(remote in net for net in networks):
        return direct_ip
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if not xff:
        return direct_ip
    forwarded = xff.split(",", 1)[0].strip()
    try:
        ipaddress.ip_address(forwarded)
        return forwarded
    except ValueError:
        return direct_ip


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
    except (ImportError, ModuleNotFoundError, AttributeError, TypeError, ValueError, OSError, ConnectionError, TimeoutError):
        logger.warning("Redis unavailable for rate limiting; using in-memory fallback.", exc_info=True)
        return None
    except Exception:
        # Catch Redis-specific exceptions (redis.exceptions.TimeoutError etc.)
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
    except (RuntimeError, OSError, TypeError, ValueError):
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
    """Record one failed login attempt for this IP.

    Includes a cap at LOGIN_FAIL_MAX to limit overshoot from concurrent
    requests that both passed the pre-screen check_login_allowed() call.
    """
    if _rate_backend() == "redis":
        count = _mark_and_count_redis(_login_key(ip), LOGIN_FAIL_WINDOW, add_event=True)
        if count is not None:
            return
    now = time.monotonic()
    with _login_lock:
        # Proactively evict stale IPs to prevent memory leak
        if len(_login_failures) > _LOGIN_MAX_IPS // 2:
            stale = [
                k for k, v in _login_failures.items()
                if not v or now - v[-1] > LOGIN_FAIL_WINDOW
            ]
            for k in stale:
                del _login_failures[k]
        if len(_login_failures) >= _LOGIN_MAX_IPS and ip not in _login_failures:
            return  # Hard cap reached; silently ignore new IPs
        bucket = _login_failures[ip]
        while bucket and now - bucket[0] > LOGIN_FAIL_WINDOW:
            bucket.popleft()
        if len(bucket) >= LOGIN_FAIL_MAX:
            return  # Already at limit; concurrent request slipped through pre-screen
        _login_failures[ip].append(now)


def check_per_route_rate_limit(ip: str, route_key: str, max_requests: int, window_seconds: int) -> bool:
    """
    Enforce a tighter per-route rate limit independent of the global middleware.
    Returns True if the request is allowed, False if the limit is exceeded.
    Uses a separate in-memory bucket keyed by (route_key, ip).
    """
    if _rate_backend() == "redis":
        redis_key = f"{(settings.RATE_LIMIT_REDIS_PREFIX or 'pc:ratelimit').strip()}:{route_key}:{ip}"
        count = _mark_and_count_redis(redis_key, window_seconds, add_event=True)
        if count is not None:
            return count <= max_requests
    now = time.monotonic()
    bucket_key = f"{route_key}:{ip}"
    with _login_lock:
        bucket = _rate_buckets[bucket_key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= max_requests:
            return False
        bucket.append(now)
    return True


def clear_login_failures(ip: str) -> None:
    """Clear failed-login history for this IP after successful authentication."""
    if _rate_backend() == "redis":
        client = _get_redis_client()
        if client is not None:
            try:
                client.delete(_login_key(ip))
            except (RuntimeError, OSError, TypeError, ValueError):
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

        client_ip = get_client_ip(request)
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        max_req = settings.RATE_LIMIT_MAX_REQUESTS
        if _rate_backend() == "redis":
            # Atomic add-then-check: add the event first, then check the
            # count.  This eliminates the race window that existed when
            # check and add were two separate calls.
            count = _mark_and_count_redis(_rate_key(client_ip), window, add_event=True)
            if count is not None:
                if count > max_req:
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
                _rate_limit_stats["allowed"] += 1
                return cast(Response, await call_next(request))

        now = time.monotonic()
        try:
            await asyncio.wait_for(_rate_limit_lock.acquire(), timeout=1.0)
        except TimeoutError:
            # Lock contention — reject instead of silently bypassing rate limit
            return JSONResponse(
                status_code=503,
                content={"detail": "Service temporarily busy. Please retry."},
                headers={"Retry-After": "2"},
            )
        try:
            # Proactively evict stale IPs to prevent unbounded memory growth
            if len(_rate_buckets) > 1000:
                stale = [
                    k for k, v in _rate_buckets.items()
                    if not v or now - v[-1] > window
                ]
                for k in stale:
                    del _rate_buckets[k]
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
