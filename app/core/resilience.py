from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def run_with_retry(
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
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except retry_exceptions as exc:
            last_exc = exc
            if i == attempts - 1:
                raise
            await asyncio.sleep(backoff_seconds * (2**i))
    assert last_exc is not None
    raise last_exc
