"""Response time SLO tracking middleware.

Logs and emits a signal when any API endpoint response exceeds the SLO
threshold (default 500ms). Feeds into the CEO health dashboard.
"""
from __future__ import annotations

import logging
import time
from typing import cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

SLO_THRESHOLD_MS = 500


class SLOTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/api/v1/"):
            return cast(Response, await call_next(request))

        start = time.perf_counter()
        response: Response = cast(Response, await call_next(request))
        duration_ms = (time.perf_counter() - start) * 1000

        if duration_ms > SLO_THRESHOLD_MS:
            org_id = self._extract_org_id(request)
            logger.warning(
                "SLO breach: %s %s took %.0fms (threshold=%dms) org_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                SLO_THRESHOLD_MS,
                org_id,
            )
            try:
                await self._emit_slo_signal(request, duration_ms, org_id)
            except Exception:
                logger.debug("SLO signal emission failed", exc_info=True)

        return response

    @staticmethod
    def _extract_org_id(request: Request) -> int | None:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        try:
            from app.core.security import decode_access_token
            payload = decode_access_token(auth_header[7:])
            return int(payload["org_id"]) if "org_id" in payload else None
        except Exception:
            return None

    @staticmethod
    async def _emit_slo_signal(request: Request, duration_ms: float, org_id: int | None) -> None:
        from app.platform.signals import (
            SLO_BREACH_DETECTED,
            SignalCategory,
            SignalEnvelope,
            publish_signal,
        )

        await publish_signal(
            SignalEnvelope(
                topic=SLO_BREACH_DETECTED,
                category=SignalCategory.EXECUTION,
                organization_id=org_id or 0,
                source="slo.middleware",
                entity_type="api_endpoint",
                payload={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "duration_ms": round(duration_ms),
                    "threshold_ms": SLO_THRESHOLD_MS,
                },
            )
        )
