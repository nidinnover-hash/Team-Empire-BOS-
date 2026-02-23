from __future__ import annotations

from contextvars import ContextVar, Token

_current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


def set_current_request_id(request_id: str | None) -> Token[str | None]:
    return _current_request_id.set(request_id)


def reset_current_request_id(token: Token[str | None]) -> None:
    _current_request_id.reset(token)


def get_current_request_id() -> str | None:
    return _current_request_id.get()
