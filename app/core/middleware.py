"""
Middleware stack:
- CorrelationIDMiddleware: attaches a per-request correlation ID.
- RateLimitMiddleware: simple in-memory sliding window rate limiter.
"""

import time
import uuid
from collections import defaultdict, deque
import logging
from urllib.parse import parse_qsl, urlencode
from typing import cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.request_context import reset_current_request_id, set_current_request_id
from app.core.security import decode_access_token

logger = logging.getLogger("request")

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


# ── Rate Limiter ──────────────────────────────────────────────────────────────
# In-memory sliding window per client IP. Resets on server restart (by design
# for a personal tool — use Redis for multi-instance deployments).

_rate_buckets: dict[str, deque] = defaultdict(deque)

# Paths exempt from rate limiting (health checks, docs)
_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")

# ── Login Failure Tracker ──────────────────────────────────────────────────────
# Sliding window per IP — resets on server restart (acceptable for a personal tool).

_login_failures: dict[str, deque] = defaultdict(deque)
LOGIN_FAIL_WINDOW = 900   # 15-minute window
LOGIN_FAIL_MAX = 10       # max failures before lockout


def check_login_allowed(ip: str) -> bool:
    """Return True if the IP is below the failed-login threshold."""
    now = time.monotonic()
    bucket = _login_failures[ip]
    while bucket and now - bucket[0] > LOGIN_FAIL_WINDOW:
        bucket.popleft()
    return len(bucket) < LOGIN_FAIL_MAX


def record_login_failure(ip: str) -> None:
    """Record one failed login attempt for this IP."""
    _login_failures[ip].append(time.monotonic())


def clear_login_failures(ip: str) -> None:
    """Clear failed-login history for this IP after successful authentication."""
    _login_failures.pop(ip, None)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return cast(Response, await call_next(request))

        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return cast(Response, await call_next(request))

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        max_req = settings.RATE_LIMIT_MAX_REQUESTS

        bucket = _rate_buckets[client_ip]
        # Drop timestamps outside the sliding window
        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= max_req:
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
        return cast(Response, await call_next(request))
