from __future__ import annotations

from typing import Any

API_CONTRACT_VERSION = "2026-02-23"

# Max characters for error/detail strings stored in DB or logs.
# Use this instead of hardcoding [:500] everywhere.
LOG_DETAIL_MAX_CHARS = 500


def error_envelope(*, code: str, detail: Any, request_id: str | None) -> dict[str, Any]:
    return {
        "code": code,
        "detail": detail,
        "request_id": request_id,
        "contract_version": API_CONTRACT_VERSION,
    }
