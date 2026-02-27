"""Shared helpers for integration connect/status/sync endpoints.

Reduces boilerplate in integration_*.py files without replacing them.
Each integration file stays independent and readable.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.audit import record_action

logger = logging.getLogger(__name__)

# Standard exception tuple for integration connect handlers
CONNECT_EXCEPTIONS = (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError)


async def handle_connect_error(
    db: AsyncSession,
    *,
    integration_type: str,
    actor: dict,
    exc: BaseException,
    detail: str = "Connection failed. Check credentials and try again.",
    request_id: str | None = None,
) -> None:
    """Log warning, record failed audit event, and raise 400."""
    logger.warning("%s connect failed: %s", integration_type, exc)
    payload: dict[str, Any] = {
        "type": integration_type,
        "status": "error",
        "error_type": type(exc).__name__,
    }
    if request_id:
        payload["request_id"] = request_id
    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json=payload,
    )
    raise HTTPException(status_code=400, detail=detail) from exc


async def audit_connect_success(
    db: AsyncSession,
    *,
    integration_type: str,
    actor: dict,
    entity_id: int | None = None,
    extra: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    """Record a successful integration connect audit event."""
    payload: dict[str, Any] = {"type": integration_type, "status": "ok"}
    if request_id:
        payload["request_id"] = request_id
    if extra:
        payload.update(extra)
    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=entity_id,
        payload_json=payload,
    )


async def audit_sync(
    db: AsyncSession,
    *,
    event_type: str,
    actor: dict,
    payload: dict[str, Any],
    request_id: str | None = None,
) -> None:
    """Record an integration sync audit event."""
    full_payload: dict[str, Any] = {"status": "ok"}
    if request_id:
        full_payload["request_id"] = request_id
    full_payload.update(payload)
    await record_action(
        db,
        event_type=event_type,
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json=full_payload,
    )


def normalize_sync_result(
    result: object,
    *,
    integration_type: str,
    required_int_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Validate sync result contract and return normalized dict."""
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=502,
            detail=f"{integration_type.capitalize()} sync returned an invalid response shape.",
        )

    error = result.get("error")
    if error:
        raise HTTPException(status_code=400, detail=str(error))

    normalized: dict[str, Any] = {"error": None}
    for field in required_int_fields:
        value = result.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(
                status_code=502,
                detail=f"{integration_type.capitalize()} sync returned invalid field '{field}'.",
            )
        normalized[field] = value
    return normalized
