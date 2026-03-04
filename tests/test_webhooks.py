"""Tests for outgoing webhook management (CRUD, dispatch, signing, alerts)."""

from __future__ import annotations

import hashlib
import hmac
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy import select

from tests.conftest import _make_auth_headers


@pytest.fixture
def _patch_webhook_session(db, monkeypatch):
    """Make webhook dispatch use the test DB session instead of AsyncSessionLocal."""
    from app.services import webhook as webhook_service

    @asynccontextmanager
    async def _test_session():
        yield db

    monkeypatch.setattr(webhook_service, "AsyncSessionLocal", _test_session)

def _ceo_headers() -> dict[str, str]:
    return _make_auth_headers(1, "ceo@org1.com", "CEO", 1)

def _org2_headers() -> dict[str, str]:
    return _make_auth_headers(2, "ceo@org2.com", "CEO", 2)

def _staff_headers() -> dict[str, str]:
    return _make_auth_headers(4, "staff@org1.com", "STAFF", 1)

BASE = "/api/v1/webhooks"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_webhook(client, url="https://example.com/hook", events=None, headers=None):
    body: dict = {"url": url}
    if events is not None:
        body["event_types"] = events
    return await client.post(BASE, json=body, headers=headers or _ceo_headers())


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.text = "ok"


# ---------------------------------------------------------------------------
# CRUD (HTTP client tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_webhook_endpoint(client):
    resp = await _create_webhook(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["url"] == "https://example.com/hook"
    assert data["is_active"] is True
    assert "signing_secret" in data
    assert len(data["signing_secret"]) == 64
    assert data["id"] > 0


@pytest.mark.asyncio
async def test_create_webhook_with_event_filter(client):
    resp = await _create_webhook(
        client,
        url="https://example.com/approvals",
        events=["approval.created", "approval.approved"],
    )
    assert resp.status_code == 201
    assert resp.json()["event_types"] == ["approval.created", "approval.approved"]


@pytest.mark.asyncio
async def test_create_webhook_rejects_invalid_event_types(client):
    resp = await _create_webhook(client, events=["nonexistent.event"])
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_webhook_rejects_localhost_targets(client):
    resp = await _create_webhook(client, url="https://localhost/hook")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_webhook_rejects_private_ip_targets(client):
    resp = await _create_webhook(client, url="https://127.0.0.1/hook")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_webhook_enforces_host_allowlist(db, monkeypatch):
    from app.services import webhook as webhook_service

    monkeypatch.setattr(
        webhook_service.settings,
        "WEBHOOK_HOST_ALLOWLIST",
        "hooks.slack.com,*.trusted.example",
    )
    with pytest.raises(ValueError, match="allowlisted"):
        await webhook_service.create_webhook_endpoint(
            db,
            organization_id=1,
            url="https://evil.example/hook",
        )

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db,
        organization_id=1,
        url="https://alerts.trusted.example/hook",
    )
    assert endpoint.id > 0


@pytest.mark.asyncio
async def test_create_webhook_rejects_dns_resolving_to_private_ip(db, monkeypatch):
    from app.services import webhook as webhook_service

    def fake_getaddrinfo(*_args, **_kwargs):
        # Simulate DNS resolving a public host to loopback.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    import socket
    monkeypatch.setattr(webhook_service.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(webhook_service.settings, "DEBUG", False)

    with pytest.raises(ValueError, match="host is not allowed"):
        await webhook_service.create_webhook_endpoint(
            db,
            organization_id=1,
            url="https://example.com/hook",
        )


@pytest.mark.asyncio
async def test_list_webhook_endpoints(client):
    await _create_webhook(client, url="https://example.com/hook1")
    await _create_webhook(client, url="https://example.com/hook2")
    resp = await client.get(BASE, headers=_ceo_headers())
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    assert "signing_secret" not in items[0]


@pytest.mark.asyncio
async def test_get_webhook_endpoint(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    resp = await client.get(f"{BASE}/{wh_id}", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json()["id"] == wh_id
    assert "signing_secret" not in resp.json()


@pytest.mark.asyncio
async def test_get_webhook_not_found(client):
    resp = await client.get(f"{BASE}/99999", headers=_ceo_headers())
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_webhook_endpoint(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    resp = await client.patch(
        f"{BASE}/{wh_id}",
        json={"url": "https://updated.example.com/hook", "is_active": False},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://updated.example.com/hook"
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_update_webhook_not_found(client):
    resp = await client.patch(
        f"{BASE}/99999",
        json={"is_active": False},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_webhook_endpoint(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    del_resp = await client.delete(f"{BASE}/{wh_id}", headers=_ceo_headers())
    assert del_resp.status_code == 204
    get_resp = await client.get(f"{BASE}/{wh_id}", headers=_ceo_headers())
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_webhook_not_found(client):
    resp = await client.delete(f"{BASE}/99999", headers=_ceo_headers())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Org isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_org_get_denied(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    resp = await client.get(f"{BASE}/{wh_id}", headers=_org2_headers())
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_delete_denied(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    resp = await client.delete(f"{BASE}/{wh_id}", headers=_org2_headers())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_cannot_create_webhook(client):
    resp = await _create_webhook(client, headers=_staff_headers())
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Dispatch (db-only, service-level tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_dispatches_to_matching_endpoints(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://a.example.com/hook",
        event_types=["approval.created"],
    )
    await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://b.example.com/hook",
        event_types=["approval.rejected"],
    )

    dispatched_urls: list[str] = []

    async def fake_post(self, url, **kwargs):
        dispatched_urls.append(url)
        return _FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"test": True}
    )

    assert "https://a.example.com/hook" in dispatched_urls
    assert "https://b.example.com/hook" not in dispatched_urls


@pytest.mark.asyncio
async def test_trigger_dispatches_to_all_when_no_filter(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://all.example.com/hook", event_types=[],
    )

    dispatched_urls: list[str] = []

    async def fake_post(self, url, **kwargs):
        dispatched_urls.append(url)
        return _FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"test": True}
    )

    assert "https://all.example.com/hook" in dispatched_urls


@pytest.mark.asyncio
async def test_trigger_skips_inactive_endpoints(db, monkeypatch):
    from app.services import webhook as webhook_service

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://inactive.example.com/hook",
    )
    await webhook_service.update_webhook_endpoint(
        db, endpoint.id, 1, is_active=False,
    )

    dispatched_urls: list[str] = []

    async def fake_post(self, url, **kwargs):
        dispatched_urls.append(url)
        return _FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"test": True}
    )

    assert "https://inactive.example.com/hook" not in dispatched_urls


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_signature_is_valid_hmac(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    _endpoint, signing_secret = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://sig.example.com/hook",
    )

    captured_headers: dict = {}
    captured_body: bytes = b""

    async def fake_post(self, url, **kwargs):
        nonlocal captured_headers, captured_body
        captured_headers = kwargs.get("headers", {})
        captured_body = kwargs.get("content", b"")
        return _FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"sig": "test"}
    )

    expected_sig = "sha256=" + hmac.new(
        signing_secret.encode("utf-8"), captured_body, hashlib.sha256
    ).hexdigest()
    assert captured_headers.get("X-Webhook-Signature-256") == expected_sig
    assert captured_headers.get("X-Webhook-Event") == "approval.created"


# ---------------------------------------------------------------------------
# Delivery log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delivery_logged_on_success(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://log.example.com/hook",
    )

    async def fake_post(self, url, **kwargs):
        return _FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"logged": True}
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert len(deliveries) >= 1
    assert deliveries[0].status == "success"
    assert deliveries[0].event == "approval.created"
    assert deliveries[0].response_status_code == 200


@pytest.mark.asyncio
async def test_delivery_records_failure_on_non_2xx(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_BACKOFF_SECONDS", 0.0)

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://fail.example.com/hook",
        max_retry_attempts=2,
    )

    async def fake_post(self, url, **kwargs):
        return _FakeResponse(500)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"fail": True}
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "dead_letter"
    assert deliveries[0].response_status_code == 500
    assert deliveries[0].attempt_count == 2


@pytest.mark.asyncio
async def test_delivery_records_failure_on_timeout(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_BACKOFF_SECONDS", 0.0)

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://timeout.example.com/hook",
        max_retry_attempts=3,
    )

    async def fake_post(self, url, **kwargs):
        raise httpx.ConnectTimeout("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"timeout": True}
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "dead_letter"
    assert deliveries[0].attempt_count == 3
    assert "ConnectTimeout" in deliveries[0].error_message


# ---------------------------------------------------------------------------
# Test endpoint (db-only to avoid monkeypatch conflict with httpx client)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_test_webhook(db, monkeypatch):
    from app.services import webhook as webhook_service

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://test.example.com/hook",
    )

    async def fake_post(self, url, **kwargs):
        return _FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await webhook_service.send_test_webhook(db, endpoint.id, 1)
    assert result["ok"] is True
    assert result["status_code"] == 200


@pytest.mark.asyncio
async def test_send_test_webhook_not_found(client):
    resp = await client.post(f"{BASE}/99999/test", headers=_ceo_headers())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Alert service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_pending_alert_creates_notification(db):
    from app.services import alert as alert_service
    from app.services import notification as notification_service

    await alert_service.send_pending_alert(
        db,
        org_id=1,
        entity_type="approval",
        entity_id=999,
        title="Test alert",
        detail="This is a test alert",
    )

    notifications = await notification_service.list_notifications(db, organization_id=1)
    matching = [n for n in notifications if n.title == "Test alert"]
    assert len(matching) == 1
    assert matching[0].severity == "warning"
    assert matching[0].source == "alert_service"


@pytest.mark.asyncio
async def test_send_pending_alert_fires_slack_when_configured(db, monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.CEO_ALERTS_SLACK_CHANNEL_ID", "C12345"
    )

    slack_calls: list[dict] = []

    async def fake_send_to_slack(db, org_id, channel_id, text):
        slack_calls.append({"channel": channel_id, "text": text})
        return {"ok": True}

    import app.services.slack_service as slack_mod

    monkeypatch.setattr(slack_mod, "send_to_slack", fake_send_to_slack)

    from app.services import alert as alert_service

    await alert_service.send_pending_alert(
        db,
        org_id=1,
        entity_type="approval",
        entity_id=1,
        title="Slack test",
        detail="Detail here",
    )

    assert len(slack_calls) == 1
    assert slack_calls[0]["channel"] == "C12345"


@pytest.mark.asyncio
async def test_send_pending_alert_skips_slack_when_no_channel(db, monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.CEO_ALERTS_SLACK_CHANNEL_ID", ""
    )

    from app.services import alert as alert_service

    await alert_service.send_pending_alert(
        db,
        org_id=1,
        entity_type="task",
        entity_id=1,
        title="No slack",
        detail="Should not send to Slack",
    )


# ---------------------------------------------------------------------------
# Background retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_delivery_sets_next_retry_at(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_BACKOFF_SECONDS", 0.0)

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://retry.example.com/hook",
    )

    async def fake_post(self, url, **kwargs):
        return _FakeResponse(500)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"retry": True},
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "failed"
    assert deliveries[0].next_retry_at is not None


@pytest.mark.asyncio
async def test_background_retry_succeeds(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_BACKOFF_SECONDS", 0.0)

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://retry-ok.example.com/hook",
    )

    call_count = 0

    async def fake_post(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _FakeResponse(500)
        return _FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"retry_ok": True},
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "failed"

    # Move next_retry_at to the past so retry picks it up
    from datetime import UTC, datetime, timedelta
    deliveries[0].next_retry_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    retried = await webhook_service.retry_failed_deliveries(db)
    assert retried == 1

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "success"
    assert deliveries[0].next_retry_at is None


@pytest.mark.asyncio
async def test_background_retry_exhausted_becomes_dead_letter(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_BACKOFF_SECONDS", 0.0)

    # Endpoint with max_retry_attempts=2 (so only 2 total attempts before dead_letter)
    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://exhaust.example.com/hook",
    )
    endpoint.max_retry_attempts = 2
    await db.commit()

    async def fake_post(self, url, **kwargs):
        return _FakeResponse(500)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"exhaust": True},
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "failed"
    assert deliveries[0].attempt_count == 1

    # Move next_retry_at to the past
    from datetime import UTC, datetime, timedelta
    deliveries[0].next_retry_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    await webhook_service.retry_failed_deliveries(db)

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "dead_letter"


@pytest.mark.asyncio
async def test_replay_dead_letter_delivery_creates_new_delivery(db, monkeypatch, _patch_webhook_session):
    from app.models.webhook import WebhookDelivery
    from app.services import webhook as webhook_service

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db,
        organization_id=1,
        url="https://deadletter.example.com/hook",
        event_types=["approval.created"],
        max_retry_attempts=1,
    )
    failed = WebhookDelivery(
        webhook_endpoint_id=endpoint.id,
        organization_id=1,
        event="approval.created",
        payload_json={"x": 1},
        status="dead_letter",
        attempt_count=1,
        max_retries=1,
        error_message="TimeoutError: request timed out",
    )
    db.add(failed)
    await db.commit()
    await db.refresh(failed)

    async def fake_post(self, url, **kwargs):
        return _FakeResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)
    replayed = await webhook_service.replay_dead_letter_delivery(
        db,
        organization_id=1,
        delivery_id=failed.id,
    )
    assert replayed is not None
    assert replayed.id != failed.id
    assert replayed.status == "success"

    rows = (
        await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_endpoint_id == endpoint.id
            )
        )
    ).scalars().all()
    assert len(rows) >= 2
    rows_by_id = {int(row.id): row for row in rows}
    assert rows_by_id[failed.id].status == "replayed"
    assert rows_by_id[replayed.id].next_retry_at is None
    assert rows_by_id[replayed.id].attempt_count >= 1


@pytest.mark.asyncio
async def test_backoff_increases_exponentially(db):
    from datetime import UTC, datetime

    from app.services.webhook import _calculate_next_retry_at

    now = datetime.now(UTC)
    retry1 = _calculate_next_retry_at(1)
    retry2 = _calculate_next_retry_at(2)
    retry3 = _calculate_next_retry_at(3)

    # Attempt 1 -> ~10s, Attempt 2 -> ~20s, Attempt 3 -> ~40s
    delta1 = (retry1 - now).total_seconds()
    delta2 = (retry2 - now).total_seconds()
    delta3 = (retry3 - now).total_seconds()

    assert 9 < delta1 < 12  # 10s + up to 10% jitter
    assert 19 < delta2 < 23  # 20s + up to 10% jitter
    assert 39 < delta3 < 45  # 40s + up to 10% jitter


@pytest.mark.asyncio
async def test_dispatch_revalidates_target_url_each_attempt(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://revalidate.example.com/hook",
    )

    call_count = 0

    def fake_validate_url(_url: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise ValueError("Webhook URL host is not allowed")

    async def fake_post(self, url, **kwargs):
        return _FakeResponse(500)

    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_DELIVERY_MAX_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(webhook_service, "_validate_url", fake_validate_url)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"check": True},
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status in {"failed", "dead_letter"}
    assert "host is not allowed" in (deliveries[0].error_message or "")


@pytest.mark.asyncio
async def test_async_queue_mode_enqueues_pending_without_network(db, monkeypatch, _patch_webhook_session):
    from app.services import webhook as webhook_service

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://queue-only.example.com/hook",
    )
    monkeypatch.setattr(webhook_service.settings, "WEBHOOK_ASYNC_DISPATCH_ONLY", True)

    async def fail_post(self, url, **kwargs):
        raise AssertionError("Network call should not be made in queue-only mode")

    monkeypatch.setattr(httpx.AsyncClient, "post", fail_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"queued": True},
    )
    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "pending"
    assert deliveries[0].attempt_count == 0
