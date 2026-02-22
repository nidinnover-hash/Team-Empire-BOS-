"""
Middleware stack:
- CorrelationIDMiddleware: attaches a per-request correlation ID.
- RateLimitMiddleware: simple in-memory sliding window rate limiter.
"""

import time
import uuid
from collections import defaultdict, deque
from typing import cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings


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
        response = cast(Response, await call_next(request))
        response.headers["X-Correlation-ID"] = correlation_id
        return response


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
