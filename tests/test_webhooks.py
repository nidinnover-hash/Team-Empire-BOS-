"""Tests for outgoing webhook management (CRUD, dispatch, signing, alerts)."""

from __future__ import annotations

import hashlib
import hmac

import httpx
import pytest

from tests.conftest import _make_auth_headers

CEO_HEADERS = _make_auth_headers(1, "ceo@org1.com", "CEO", 1)
ORG2_HEADERS = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)
STAFF_HEADERS = _make_auth_headers(4, "staff@org1.com", "STAFF", 1)

BASE = "/api/v1/webhooks"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_webhook(client, url="https://example.com/hook", events=None, headers=None):
    body: dict = {"url": url}
    if events is not None:
        body["event_types"] = events
    return await client.post(BASE, json=body, headers=headers or CEO_HEADERS)


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
async def test_list_webhook_endpoints(client):
    await _create_webhook(client, url="https://example.com/hook1")
    await _create_webhook(client, url="https://example.com/hook2")
    resp = await client.get(BASE, headers=CEO_HEADERS)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    assert "signing_secret" not in items[0]


@pytest.mark.asyncio
async def test_get_webhook_endpoint(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    resp = await client.get(f"{BASE}/{wh_id}", headers=CEO_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == wh_id
    assert "signing_secret" not in resp.json()


@pytest.mark.asyncio
async def test_get_webhook_not_found(client):
    resp = await client.get(f"{BASE}/99999", headers=CEO_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_webhook_endpoint(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    resp = await client.patch(
        f"{BASE}/{wh_id}",
        json={"url": "https://updated.example.com/hook", "is_active": False},
        headers=CEO_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://updated.example.com/hook"
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_update_webhook_not_found(client):
    resp = await client.patch(
        f"{BASE}/99999",
        json={"is_active": False},
        headers=CEO_HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_webhook_endpoint(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    del_resp = await client.delete(f"{BASE}/{wh_id}", headers=CEO_HEADERS)
    assert del_resp.status_code == 204
    get_resp = await client.get(f"{BASE}/{wh_id}", headers=CEO_HEADERS)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_webhook_not_found(client):
    resp = await client.delete(f"{BASE}/99999", headers=CEO_HEADERS)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Org isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_org_get_denied(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    resp = await client.get(f"{BASE}/{wh_id}", headers=ORG2_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_delete_denied(client):
    create_resp = await _create_webhook(client)
    wh_id = create_resp.json()["id"]
    resp = await client.delete(f"{BASE}/{wh_id}", headers=ORG2_HEADERS)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_cannot_create_webhook(client):
    resp = await _create_webhook(client, headers=STAFF_HEADERS)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Dispatch (db-only, service-level tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_dispatches_to_matching_endpoints(db, monkeypatch):
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
async def test_trigger_dispatches_to_all_when_no_filter(db, monkeypatch):
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
async def test_webhook_signature_is_valid_hmac(db, monkeypatch):
    from app.services import webhook as webhook_service

    endpoint, signing_secret = await webhook_service.create_webhook_endpoint(
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
async def test_delivery_logged_on_success(db, monkeypatch):
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
async def test_delivery_records_failure_on_non_2xx(db, monkeypatch):
    from app.services import webhook as webhook_service

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://fail.example.com/hook",
    )

    async def fake_post(self, url, **kwargs):
        return _FakeResponse(500)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"fail": True}
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "failed"
    assert deliveries[0].response_status_code == 500


@pytest.mark.asyncio
async def test_delivery_records_failure_on_timeout(db, monkeypatch):
    from app.services import webhook as webhook_service

    endpoint, _ = await webhook_service.create_webhook_endpoint(
        db, organization_id=1, url="https://timeout.example.com/hook",
    )

    async def fake_post(self, url, **kwargs):
        raise httpx.ConnectTimeout("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await webhook_service.trigger_org_webhooks(
        db, organization_id=1, event="approval.created", payload={"timeout": True}
    )

    deliveries = await webhook_service.list_deliveries(db, endpoint.id, 1)
    assert deliveries[0].status == "failed"
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
    resp = await client.post(f"{BASE}/99999/test", headers=CEO_HEADERS)
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
