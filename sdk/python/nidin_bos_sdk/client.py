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

    def agent_chat(self, payload: models.AgentChatRequest) -> models.AgentChatResponse:
        data = self._request_json(
            method="POST",
            path="/api/v1/agents/chat",
            json_body=cast(dict[str, Any], payload),
            expected_status=200,
        )
        return cast(models.AgentChatResponse, data)

    def agent_multi_turn(self, payload: models.AgentChatRequest) -> models.MultiTurnResponse:
        data = self._request_json(
            method="POST",
            path="/api/v1/agents/multi-turn",
            json_body=cast(dict[str, Any], payload),
            expected_status=200,
        )
        return cast(models.MultiTurnResponse, data)

    # BEGIN GENERATED OPERATIONS
    def delete_api_v1_api_keys_key_id(self, key_id: Any) -> Any:
        path = f"/api/v1/api-keys/{key_id}"
        params = None
        return self._request_json(
            method="DELETE",
            path=path,
            json_body=None,
            params=params,
            expected_status=204,
        )

    def delete_api_v1_approvals_approval_patterns_pattern_id(self, pattern_id: Any) -> Any:
        path = f"/api/v1/approvals/approval-patterns/{pattern_id}"
        params = None
        return self._request_json(
            method="DELETE",
            path=path,
            json_body=None,
            params=params,
            expected_status=204,
        )

    def delete_api_v1_automations_triggers_trigger_id(self, trigger_id: Any) -> Any:
        path = f"/api/v1/automations/triggers/{trigger_id}"
        params = None
        return self._request_json(
            method="DELETE",
            path=path,
            json_body=None,
            params=params,
            expected_status=204,
        )

    def delete_api_v1_tasks_task_id(self, task_id: Any) -> Any:
        path = f"/api/v1/tasks/{task_id}"
        params = None
        return self._request_json(
            method="DELETE",
            path=path,
            json_body=None,
            params=params,
            expected_status=204,
        )

    def delete_api_v1_webhooks_endpoint_id(self, endpoint_id: Any) -> Any:
        path = f"/api/v1/webhooks/{endpoint_id}"
        params = None
        return self._request_json(
            method="DELETE",
            path=path,
            json_body=None,
            params=params,
            expected_status=204,
        )

    def get_api_v1_api_keys(self) -> Any:
        path = "/api/v1/api-keys"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_approvals(self, status: Any | None = None, limit: Any | None = None, offset: Any | None = None) -> Any:
        path = "/api/v1/approvals"
        params = {
            "status": status,
            "limit": limit,
            "offset": offset,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_approvals_approval_patterns(self) -> Any:
        path = "/api/v1/approvals/approval-patterns"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_approvals_timeline(self, limit: Any | None = None, offset: Any | None = None) -> Any:
        path = "/api/v1/approvals/timeline"
        params = {
            "limit": limit,
            "offset": offset,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_auth_me(self) -> Any:
        path = "/api/v1/auth/me"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_automations_triggers(self, active_only: Any | None = None, limit: Any | None = None) -> Any:
        path = "/api/v1/automations/triggers"
        params = {
            "active_only": active_only,
            "limit": limit,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_automations_triggers_trigger_id(self, trigger_id: Any) -> Any:
        path = f"/api/v1/automations/triggers/{trigger_id}"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_automations_workflows(self, status: Any | None = None, limit: Any | None = None) -> Any:
        path = "/api/v1/automations/workflows"
        params = {
            "status": status,
            "limit": limit,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_automations_workflows_workflow_id(self, workflow_id: Any) -> Any:
        path = f"/api/v1/automations/workflows/{workflow_id}"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_orgs(self) -> Any:
        path = "/api/v1/orgs"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_orgs_org_id_feature_flags(self, org_id: Any) -> Any:
        path = f"/api/v1/orgs/{org_id}/feature-flags"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_orgs_org_id_members(self, org_id: Any) -> Any:
        path = f"/api/v1/orgs/{org_id}/members"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_tasks(self, project_id: Any | None = None, category: Any | None = None, is_done: Any | None = None, limit: Any | None = None, offset: Any | None = None) -> Any:
        path = "/api/v1/tasks"
        params = {
            "project_id": project_id,
            "category": category,
            "is_done": is_done,
            "limit": limit,
            "offset": offset,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_webhooks(self, limit: Any | None = None, offset: Any | None = None) -> Any:
        path = "/api/v1/webhooks"
        params = {
            "limit": limit,
            "offset": offset,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_webhooks_deliveries_all(self, event: Any | None = None, status: Any | None = None, limit: Any | None = None, offset: Any | None = None) -> Any:
        path = "/api/v1/webhooks/deliveries/all"
        params = {
            "event": event,
            "status": status,
            "limit": limit,
            "offset": offset,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_webhooks_deliveries_dead_letter(self, limit: Any | None = None, offset: Any | None = None) -> Any:
        path = "/api/v1/webhooks/deliveries/dead-letter"
        params = {
            "limit": limit,
            "offset": offset,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_webhooks_endpoint_id(self, endpoint_id: Any) -> Any:
        path = f"/api/v1/webhooks/{endpoint_id}"
        params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def get_api_v1_webhooks_endpoint_id_deliveries(self, endpoint_id: Any, limit: Any | None = None, offset: Any | None = None) -> Any:
        path = f"/api/v1/webhooks/{endpoint_id}/deliveries"
        params = {
            "limit": limit,
            "offset": offset,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            params = None
        return self._request_json(
            method="GET",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def patch_api_v1_approvals_approval_patterns_pattern_id(self, pattern_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/approvals/approval-patterns/{pattern_id}"
        params = None
        return self._request_json(
            method="PATCH",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def patch_api_v1_automations_triggers_trigger_id(self, trigger_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/automations/triggers/{trigger_id}"
        params = None
        return self._request_json(
            method="PATCH",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def patch_api_v1_orgs_org_id(self, org_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/orgs/{org_id}"
        params = None
        return self._request_json(
            method="PATCH",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def patch_api_v1_orgs_org_id_feature_flags(self, org_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/orgs/{org_id}/feature-flags"
        params = None
        return self._request_json(
            method="PATCH",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def patch_api_v1_tasks_task_id(self, task_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/tasks/{task_id}"
        params = None
        return self._request_json(
            method="PATCH",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def patch_api_v1_webhooks_endpoint_id(self, endpoint_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/webhooks/{endpoint_id}"
        params = None
        return self._request_json(
            method="PATCH",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def post_api_v1_api_keys(self, payload: dict[str, Any] | None = None) -> Any:
        path = "/api/v1/api-keys"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=201,
        )

    def post_api_v1_approvals_approval_id_approve(self, approval_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/approvals/{approval_id}/approve"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def post_api_v1_approvals_approval_id_reject(self, approval_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/approvals/{approval_id}/reject"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def post_api_v1_approvals_request(self, payload: dict[str, Any] | None = None) -> Any:
        path = "/api/v1/approvals/request"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=201,
        )

    def post_api_v1_auth_login(self) -> Any:
        path = "/api/v1/auth/login"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def post_api_v1_automations_triggers(self, payload: dict[str, Any] | None = None) -> Any:
        path = "/api/v1/automations/triggers"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=201,
        )

    def post_api_v1_automations_workflows(self, payload: dict[str, Any] | None = None) -> Any:
        path = "/api/v1/automations/workflows"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=201,
        )

    def post_api_v1_automations_workflows_workflow_id_advance(self, workflow_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/automations/workflows/{workflow_id}/advance"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=200,
        )

    def post_api_v1_automations_workflows_workflow_id_run(self, workflow_id: Any) -> Any:
        path = f"/api/v1/automations/workflows/{workflow_id}/run"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def post_api_v1_automations_workflows_workflow_id_start(self, workflow_id: Any) -> Any:
        path = f"/api/v1/automations/workflows/{workflow_id}/start"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def post_api_v1_orgs(self, payload: dict[str, Any] | None = None) -> Any:
        path = "/api/v1/orgs"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=201,
        )

    def post_api_v1_orgs_org_id_members(self, org_id: Any, payload: dict[str, Any] | None = None) -> Any:
        path = f"/api/v1/orgs/{org_id}/members"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=201,
        )

    def post_api_v1_tasks(self, payload: dict[str, Any] | None = None) -> Any:
        path = "/api/v1/tasks"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=201,
        )

    def post_api_v1_webhooks(self, payload: dict[str, Any] | None = None) -> Any:
        path = "/api/v1/webhooks"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=payload,
            params=params,
            expected_status=201,
        )

    def post_api_v1_webhooks_deliveries_delivery_id_replay(self, delivery_id: Any) -> Any:
        path = f"/api/v1/webhooks/deliveries/{delivery_id}/replay"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )

    def post_api_v1_webhooks_endpoint_id_test(self, endpoint_id: Any) -> Any:
        path = f"/api/v1/webhooks/{endpoint_id}/test"
        params = None
        return self._request_json(
            method="POST",
            path=path,
            json_body=None,
            params=params,
            expected_status=200,
        )
    # END GENERATED OPERATIONS
