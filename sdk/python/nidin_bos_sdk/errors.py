from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SDKError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class APIError(SDKError):
    status_code: int
    detail: str | None = None
    request_id: str | None = None
    body: Any = None

    @classmethod
    def from_response(
        cls,
        *,
        status_code: int,
        body: Any,
        request_id: str | None = None,
    ) -> APIError:
        detail: str | None = None
        if isinstance(body, dict):
            maybe_detail = body.get("detail")
            detail = str(maybe_detail) if maybe_detail is not None else None
        return cls(
            message=f"API request failed with status {status_code}",
            status_code=status_code,
            detail=detail,
            request_id=request_id,
            body=body,
        )


@dataclass(slots=True)
class RateLimitError(APIError):
    retry_after_seconds: float | None = None


@dataclass(slots=True)
class QuotaExceededError(RateLimitError):
    pass
