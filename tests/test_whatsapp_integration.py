import hmac
import json
from hashlib import sha256

from app.api.v1.endpoints import integrations as integrations_endpoint
from app.core import oauth_nonce
from app.core.security import create_access_token


def _auth_headers(user_id: int, email: str, role: str, org_id: int) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def test_whatsapp_connect_and_test_success(client, monkeypatch):
    async def fake_get_phone_number_details(*_args, **_kwargs):
        return {"id": "pnid", "display_phone_number": "+15551234567"}

    monkeypatch.setattr(
        integrations_endpoint,
        "get_phone_number_details",
        fake_get_phone_number_details,
    )

    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "whatsapp_business",
            "config_json": {
                "access_token": "wa-token",
                "phone_number_id": "pnid",
            },
        },
        headers=headers,
    )
    assert connected.status_code == 201
    assert connected.json()["config_json"]["access_token"] == "***"

    integration_id = connected.json()["id"]
    tested = await client.post(f"/api/v1/integrations/{integration_id}/test", headers=headers)
    assert tested.status_code == 200
    assert tested.json()["status"] == "ok"


async def test_whatsapp_send_test_message_success(client, monkeypatch):
    async def fake_send_text_message(*_args, **_kwargs):
        return {"messages": [{"id": "wamid.123"}]}

    monkeypatch.setattr(
        integrations_endpoint,
        "send_text_message",
        fake_send_text_message,
    )

    headers = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "whatsapp_business",
            "config_json": {
                "access_token": "wa-token",
                "phone_number_id": "pnid",
            },
        },
        headers=headers,
    )
    assert connected.status_code == 201

    sent = await client.post(
        "/api/v1/integrations/whatsapp/send-test",
        json={"to": "15551234567", "body": "hello"},
        headers=headers,
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "queued"
    assert body["message_id"] == "wamid.123"


async def test_whatsapp_webhook_verify_success(client, monkeypatch):
    monkeypatch.setattr(integrations_endpoint.settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verify-me")
    response = await client.get(
        "/api/v1/integrations/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=abc123"
    )
    assert response.status_code == 200
    assert response.text == "abc123"


async def test_whatsapp_webhook_replay_detected_when_signature_reused(client, monkeypatch):
    monkeypatch.setattr(integrations_endpoint.settings, "WHATSAPP_APP_SECRET", "wa-app-secret")
    monkeypatch.setattr(integrations_endpoint.settings, "WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS", 300)
    oauth_nonce._used_nonces.clear()
    oauth_nonce._redis_initialized = False
    oauth_nonce._redis_client = None

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "1234567890"},
                            "messages": [{"id": "wamid.REPLAY1"}],
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload, separators=(",", ":"))
    signature = "sha256=" + hmac.new(
        b"wa-app-secret",
        raw.encode("utf-8"),
        sha256,
    ).hexdigest()
    headers = {"X-Hub-Signature-256": signature, "Content-Type": "application/json"}

    first = await client.post("/api/v1/integrations/whatsapp/webhook", content=raw, headers=headers)
    assert first.status_code == 200

    second = await client.post("/api/v1/integrations/whatsapp/webhook", content=raw, headers=headers)
    assert second.status_code == 409
