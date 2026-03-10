"""Centralized mutation audit middleware.

Automatically records an audit event for every successful (2xx) mutation
(POST / PUT / PATCH / DELETE) on ``/api/v1/`` routes. Extracts actor
information from the Authorization header JWT.

This replaces the need to call ``record_action()`` in every individual
endpoint handler — audit coverage is guaranteed at the infrastructure layer.
"""
from __future__ import annotations

import logging
from typing import cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that already have their own explicit record_action() calls or should
# be excluded to prevent duplicate audit entries.
_SKIP_PREFIXES = (
    # Pre-existing endpoints with explicit audit calls
    "/api/v1/admin",
    "/api/v1/agents",
    "/api/v1/approvals",
    "/api/v1/auth",
    "/api/v1/automations",
    "/api/v1/automation",
    "/api/v1/briefings",
    "/api/v1/bulk",
    "/api/v1/campaigns",
    "/api/v1/coaching",
    "/api/v1/contacts",
    "/api/v1/control",
    "/api/v1/data-collection",
    "/api/v1/deals",
    "/api/v1/decision-cards",
    "/api/v1/departments",
    "/api/v1/empire-digital",
    "/api/v1/github",
    "/api/v1/goals",
    "/api/v1/governance",
    "/api/v1/health",
    "/api/v1/integrations",
    "/api/v1/locations",
    "/api/v1/media",
    "/api/v1/memory",
    "/api/v1/mfa",
    "/api/v1/notes",
    "/api/v1/ops",
    "/api/v1/organizations",
    "/api/v1/performance",
    "/api/v1/playbooks",
    "/api/v1/projects",
    "/api/v1/quotes",
    "/api/v1/share-packets",
    "/api/v1/slack",
    "/api/v1/social",
    "/api/v1/surveys",
    "/api/v1/tasks",
    "/api/v1/users",
    "/api/v1/webhooks",
    "/api/v1/workspaces",
)


def _derive_event_type(method: str, path: str) -> str:
    """Derive a human-readable event_type from HTTP method + path.

    Examples:
        POST /api/v1/quotes         -> quote_created
        PUT  /api/v1/quotes/5       -> quote_updated
        DELETE /api/v1/quotes/5     -> quote_deleted
    """
    # Strip /api/v1/ prefix and split
    trimmed = path.removeprefix("/api/v1/").rstrip("/")
    segments = trimmed.split("/")

    # Find the resource name (first non-numeric, non-param segment)
    resource = segments[0] if segments else "resource"
    # Normalize: "product-bundles" -> "product_bundle"
    resource = resource.replace("-", "_")
    if resource.endswith("s") and not resource.endswith("ss"):
        resource = resource[:-1]  # naive singularize

    # Determine action suffix from trailing segments
    # e.g. /quotes/5/items -> "quote_item_created"
    # e.g. /deal-dependencies/1/resolve -> "deal_dependency_resolved"
    action_segment = None
    if len(segments) >= 3:
        last = segments[-1]
        if not last.isdigit():
            action_segment = last.replace("-", "_")

    method_map = {"POST": "created", "PUT": "updated", "PATCH": "updated", "DELETE": "deleted"}
    verb = method_map.get(method, "mutated")

    if action_segment:
        return f"{resource}_{action_segment}"
    return f"{resource}_{verb}"


def _extract_entity_id(path: str) -> int | None:
    """Try to extract an integer entity ID from the path."""
    segments = path.rstrip("/").split("/")
    for seg in reversed(segments):
        if seg.isdigit():
            return int(seg)
    return None


class MutationAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in _MUTATION_METHODS:
            return cast(Response, await call_next(request))

        path = request.url.path
        if not path.startswith("/api/v1/"):
            return cast(Response, await call_next(request))

        if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
            return cast(Response, await call_next(request))

        response: Response = cast(Response, await call_next(request))

        # Only audit successful mutations
        if not (200 <= response.status_code < 300):
            return response

        # Extract actor from JWT — best-effort, don't block the response
        try:
            await self._record_audit(request, response, path)
        except Exception:
            logger.debug("Mutation audit failed for %s %s", request.method, path, exc_info=True)

        return response

    async def _record_audit(self, request: Request, response: Response, path: str) -> None:
        from app.core.security import decode_access_token

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return

        token = auth_header[7:]
        try:
            payload = decode_access_token(token)
        except (ValueError, Exception):
            return

        actor_user_id = payload.get("id") or payload.get("sub")
        org_id = payload.get("org_id")
        if not actor_user_id or not org_id:
            return

        event_type = _derive_event_type(request.method, path)
        entity_id = _extract_entity_id(path)

        # Derive entity_type from path
        trimmed = path.removeprefix("/api/v1/").rstrip("/")
        entity_type = trimmed.split("/")[0].replace("-", "_") if trimmed else None

        from app.db.session import get_session_factory
        from app.logs.audit import record_action

        async with get_session_factory()() as db:
            await record_action(
                db,
                event_type=event_type,
                actor_user_id=int(actor_user_id),
                organization_id=int(org_id),
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json={
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                },
            )
