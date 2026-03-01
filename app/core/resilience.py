from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

_retry_stats: dict[str, int] = {
    "attempts": 0,
    "retries": 0,
    "failures": 0,
}


class IntegrationSyncError(Exception):
    """Typed integration sync error with provider/code metadata."""

    def __init__(self, provider: str, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    timeout_seconds: float = 10.0
    backoff_seconds: float = 0.3
    retry_exceptions: tuple[type[Exception], ...] = (Exception,)


def get_retry_stats() -> dict[str, int]:
    return dict(_retry_stats)


async def run_with_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    timeout_seconds: float = 10.0,
    backoff_seconds: float = 0.3,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last_exc: Exception | None = None
    for i in range(attempts):
        _retry_stats["attempts"] += 1
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except retry_exceptions as exc:
            last_exc = exc
            if i == attempts - 1:
                _retry_stats["failures"] += 1
                raise
            _retry_stats["retries"] += 1
            await asyncio.sleep(backoff_seconds * (2**i))
    if last_exc is None:
        raise RuntimeError("run_with_retry exhausted all attempts without capturing an exception")
    raise last_exc


def error_details(exc: Exception) -> dict[str, object]:
    payload: dict[str, object] = {
        "error_type": type(exc).__name__,
        "message": str(exc)[:500],
    }
    if isinstance(exc, IntegrationSyncError):
        payload["provider"] = exc.provider
        payload["code"] = exc.code
        payload["retryable"] = exc.retryable
    return payload
