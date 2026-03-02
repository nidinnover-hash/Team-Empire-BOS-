from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import httpx
import pytest

SDK_PYTHON = Path(__file__).resolve().parents[1] / "sdk" / "python"
if str(SDK_PYTHON) not in sys.path:
    sys.path.insert(0, str(SDK_PYTHON))

_sdk = import_module("nidin_bos_sdk")
_sdk_errors = import_module("nidin_bos_sdk.errors")
NidinBOSClient = _sdk.NidinBOSClient
QuotaExceededError = _sdk_errors.QuotaExceededError
RateLimitError = _sdk_errors.RateLimitError


def _response(
    status_code: int,
    *,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=body if body is not None else {},
        headers=headers,
        request=httpx.Request("GET", "http://localhost/test"),
    )


def test_python_sdk_raises_quota_error_and_exposes_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    client = NidinBOSClient(base_url="http://localhost", api_key="nbos_test", max_retries=0)

    def _fake_request(*args, **kwargs):
        return _response(
            429,
            body={"detail": "Daily quota exceeded for API key"},
            headers={"Retry-After": "12", "X-Correlation-ID": "req_123"},
        )

    monkeypatch.setattr(client._http, "request", _fake_request)

    with pytest.raises(QuotaExceededError) as exc:
        client.list_tasks()

    assert exc.value.status_code == 429
    assert exc.value.retry_after_seconds == 12.0
    assert exc.value.request_id == "req_123"
    client.close()


def test_python_sdk_raises_rate_limit_error_for_non_quota_429(monkeypatch: pytest.MonkeyPatch) -> None:
    client = NidinBOSClient(base_url="http://localhost", api_key="nbos_test", max_retries=0)

    def _fake_request(*args, **kwargs):
        return _response(429, body={"detail": "Too many requests right now"})

    monkeypatch.setattr(client._http, "request", _fake_request)

    with pytest.raises(RateLimitError):
        client.list_tasks()
    client.close()


def test_python_sdk_emits_request_events(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []
    client = NidinBOSClient(
        base_url="http://localhost",
        api_key="nbos_test",
        max_retries=0,
        on_request_event=events.append,
    )

    def _fake_request(*args, **kwargs):
        return _response(200, body=[{"id": 1, "title": "x"}], headers={"X-Correlation-ID": "req_ok"})

    monkeypatch.setattr(client._http, "request", _fake_request)
    tasks = client.list_tasks()
    client.close()

    assert isinstance(tasks, list)
    assert len(events) == 1
    event = events[0]
    assert event["method"] == "GET"
    assert event["path"] == "/api/v1/tasks"
    assert event["status_code"] == 200
    assert event["request_id"] == "req_ok"
