from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Literal, cast

import httpx

from . import models
from .errors import APIError, QuotaExceededError, RateLimitError

RequestEvent = dict[str, Any]
RequestEventHook = Callable[[RequestEvent], None]


def _parse_retry_after_seconds(header_value: str | None) -> float | None:
    if not header_value:
        return None
    try:
        seconds = float(header_value.strip())
    except ValueError:
        return None
    if seconds < 0:
        return None
    return seconds


class NidinBOSClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        on_request_event: RequestEventHook | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self._on_request_event = on_request_event
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def _emit_request_event(self, event: RequestEvent) -> None:
        if self._on_request_event is None:
            return
        self._on_request_event(event)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> NidinBOSClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _request_json(
        self,
        *,
        method: Literal["GET", "POST", "PATCH", "DELETE"],
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expected_status: int | tuple[int, ...] = 200,
    ) -> Any:
        expected: tuple[int, ...] = (
            (expected_status,) if isinstance(expected_status, int) else expected_status
        )
        last_error: APIError | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            response = self._http.request(method, path, json=json_body, params=params)
            duration_ms = (time.perf_counter() - started) * 1000.0
            if response.status_code in expected:
                self._emit_request_event(
                    {
                        "method": method,
                        "path": path,
                        "attempt": attempt + 1,
                        "status_code": response.status_code,
                        "duration_ms": round(duration_ms, 3),
                        "request_id": response.headers.get("X-Correlation-ID"),
                        "retriable": False,
                        "retried": attempt > 0,
                        "error_type": None,
                    }
                )
                if response.content:
                    return response.json()
                return None

            body: Any
            try:
                body = response.json()
            except ValueError:
                body = {"detail": response.text}
            request_id = response.headers.get("X-Correlation-ID")
            is_429 = response.status_code == 429
            retry_after = _parse_retry_after_seconds(response.headers.get("Retry-After"))
            quota_exceeded = False
            if isinstance(body, dict):
                detail = str(body.get("detail", "")).lower()
                quota_exceeded = "quota" in detail and "exceed" in detail
            if is_429:
                if quota_exceeded:
                    last_error = QuotaExceededError(
                        message="Daily quota exceeded",
                        status_code=429,
                        detail=str(body.get("detail")) if isinstance(body, dict) else None,
                        request_id=request_id,
                        body=body,
                        retry_after_seconds=retry_after,
                    )
                else:
                    last_error = RateLimitError(
                        message="Rate limited by API",
                        status_code=429,
                        detail=str(body.get("detail")) if isinstance(body, dict) else None,
                        request_id=request_id,
                        body=body,
                        retry_after_seconds=retry_after,
                    )
            else:
                last_error = APIError.from_response(
                    status_code=response.status_code,
                    body=body,
                    request_id=request_id,
                )

            retriable = response.status_code in {429, 502, 503, 504}
            self._emit_request_event(
                {
                    "method": method,
                    "path": path,
                    "attempt": attempt + 1,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 3),
                    "request_id": request_id,
                    "retriable": retriable,
                    "retried": attempt > 0,
                    "error_type": type(last_error).__name__,
                }
            )
            if not retriable or attempt >= self.max_retries:
                break
            delay = retry_after if retry_after is not None else self.backoff_seconds * (2**attempt)
            if delay > 0:
                time.sleep(delay)

        assert last_error is not None
        raise last_error

    def auth_me(self) -> models.UserMeRead:
        data = self._request_json(method="GET", path="/api/v1/auth/me", expected_status=200)
        return cast(models.UserMeRead, data)

    def list_api_keys(self) -> models.ApiKeyListResponse:
        data = self._request_json(method="GET", path="/api/v1/api-keys", expected_status=200)
        return cast(models.ApiKeyListResponse, data)

    def create_api_key(self, payload: models.ApiKeyCreate) -> models.ApiKeyCreateResponse:
        data = self._request_json(
            method="POST",
            path="/api/v1/api-keys",
            json_body=cast(dict[str, Any], payload),
            expected_status=201,
        )
        return cast(models.ApiKeyCreateResponse, data)

    def revoke_api_key(self, key_id: int) -> None:
        self._request_json(
            method="DELETE",
            path=f"/api/v1/api-keys/{int(key_id)}",
            expected_status=(200, 204),
        )

    def list_webhooks(self) -> models.WebhookEndpointListResponse:
        data = self._request_json(method="GET", path="/api/v1/webhooks", expected_status=200)
        return cast(models.WebhookEndpointListResponse, data)

    def create_webhook(
        self,
        payload: models.WebhookEndpointCreate,
    ) -> models.WebhookEndpointCreateResponse:
        data = self._request_json(
            method="POST",
            path="/api/v1/webhooks",
            json_body=cast(dict[str, Any], payload),
            expected_status=201,
        )
        return cast(models.WebhookEndpointCreateResponse, data)

    def list_webhook_deliveries(
        self,
        endpoint_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> models.WebhookDeliveryListResponse:
        data = self._request_json(
            method="GET",
            path=f"/api/v1/webhooks/{int(endpoint_id)}/deliveries",
            params={"limit": int(limit), "offset": int(offset)},
            expected_status=200,
        )
        return cast(models.WebhookDeliveryListResponse, data)

    def list_tasks(self) -> list[models.TaskRead]:
        data = self._request_json(method="GET", path="/api/v1/tasks", expected_status=200)
        return cast(list[models.TaskRead], data)

    def create_task(self, payload: models.TaskCreate) -> models.TaskRead:
        data = self._request_json(
            method="POST",
            path="/api/v1/tasks",
            json_body=cast(dict[str, Any], payload),
            expected_status=201,
        )
        return cast(models.TaskRead, data)

    def update_task(self, task_id: int, payload: models.TaskUpdate) -> models.TaskRead:
        data = self._request_json(
            method="PATCH",
            path=f"/api/v1/tasks/{int(task_id)}",
            json_body=cast(dict[str, Any], payload),
            expected_status=200,
        )
        return cast(models.TaskRead, data)

    def list_approvals(self) -> list[models.ApprovalRead]:
        data = self._request_json(method="GET", path="/api/v1/approvals", expected_status=200)
        return cast(list[models.ApprovalRead], data)

    def approve_approval(
        self,
        approval_id: int,
        payload: models.ApprovalDecision,
    ) -> models.ApprovalRead:
        data = self._request_json(
            method="POST",
            path=f"/api/v1/approvals/{int(approval_id)}/approve",
            json_body=cast(dict[str, Any], payload),
            expected_status=200,
        )
        return cast(models.ApprovalRead, data)

    def list_organizations(self) -> list[dict[str, Any]]:
        data = self._request_json(method="GET", path="/api/v1/orgs", expected_status=200)
        return cast(list[dict[str, Any]], data)

    def list_automation_triggers(self) -> list[dict[str, Any]]:
        data = self._request_json(
            method="GET",
            path="/api/v1/automations/triggers",
            expected_status=200,
        )
        return cast(list[dict[str, Any]], data)

    def list_automation_workflows(self) -> list[dict[str, Any]]:
        data = self._request_json(
            method="GET",
            path="/api/v1/automations/workflows",
            expected_status=200,
        )
        return cast(list[dict[str, Any]], data)
