import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import cast

from app.core.config import settings
from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.email import Email


async def _seed_email_for_org1(
    gmail_id: str = "unified-email-1",
    from_address: str = "lead@example.com",
    is_read: bool = False,
) -> int:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        email = Email(
            organization_id=1,
            gmail_id=gmail_id,
            thread_id="thread-unified-1",
            from_address=from_address,
            to_address="owner@example.com",
            subject="Need update",
            body_text="Please share the latest status.",
            received_at=datetime.now(UTC),
            is_read=is_read,
            reply_sent=False,
            created_at=datetime.now(UTC),
        )
        session.add(email)
        await session.commit()
        await session.refresh(email)
        return cast(int, email.id)
    finally:
        await agen.aclose()


async def _post_whatsapp_webhook(client, payload: dict) -> object:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    secret = (settings.WHATSAPP_APP_SECRET or "").encode("utf-8")
    signature = "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest()
    return await client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )


async def test_unified_inbox_merges_email_and_whatsapp(client):
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "whatsapp_business",
            "config_json": {
                "access_token": "wa-token",
                "phone_number_id": "1234567890",
            },
        },
    )
    assert connected.status_code == 201

    email_id = await _seed_email_for_org1()
    assert email_id > 0

    webhook = await _post_whatsapp_webhook(
        client,
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "+15550001111",
                                    "phone_number_id": "1234567890",
                                },
                                "messages": [
                                    {
                                        "from": "15551234567",
                                        "id": "wamid.TEST123",
                                        "timestamp": str(int(datetime.now(UTC).timestamp())),
                                        "type": "text",
                                        "text": {"body": "Hi there"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        },
    )
    assert webhook.status_code == 200
    assert webhook.json()["stored"] >= 1

    response = await client.get("/api/v1/inbox/unified?limit=20")
    assert response.status_code == 200
    items = response.json()
    assert any(i["channel"] == "email" for i in items)
    assert any(i["channel"] == "whatsapp" for i in items)


async def test_unified_conversations_groups_items(client):
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "whatsapp_business",
            "config_json": {
                "access_token": "wa-token",
                "phone_number_id": "1234567890",
            },
        },
    )
    assert connected.status_code == 201

    await _seed_email_for_org1(gmail_id="unified-email-2", from_address="lead@example.com", is_read=False)
    await _seed_email_for_org1(gmail_id="unified-email-3", from_address="lead@example.com", is_read=False)

    for wa_id in ("wamid.TEST201", "wamid.TEST202"):
        webhook = await _post_whatsapp_webhook(
            client,
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {
                                        "display_phone_number": "+15550001111",
                                        "phone_number_id": "1234567890",
                                    },
                                    "messages": [
                                        {
                                            "from": "15551234567",
                                            "id": wa_id,
                                            "timestamp": str(int(datetime.now(UTC).timestamp())),
                                            "type": "text",
                                            "text": {"body": f"Hi {wa_id}"},
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ]
            },
        )
        assert webhook.status_code == 200

    response = await client.get("/api/v1/inbox/conversations?limit=20")
    assert response.status_code == 200
    conversations = response.json()

    email_conv = next(c for c in conversations if c["channel"] == "email")
    assert email_conv["message_count"] >= 2
    assert email_conv["unread_count"] >= 2

    wa_conv = next(c for c in conversations if c["channel"] == "whatsapp")
    assert wa_conv["message_count"] >= 2


async def test_conversation_assign_and_state_update(client):
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "whatsapp_business",
            "config_json": {
                "access_token": "wa-token",
                "phone_number_id": "1234567890",
            },
        },
    )
    assert connected.status_code == 201

    await _seed_email_for_org1(gmail_id="unified-email-assign", from_address="owner-test@example.com", is_read=False)

    conversations_resp = await client.get("/api/v1/inbox/conversations?limit=20")
    assert conversations_resp.status_code == 200
    conversations = conversations_resp.json()
    email_conv = next(c for c in conversations if c["channel"] == "email" and c["participant"] == "owner-test@example.com")
    convo_id = email_conv["conversation_id"]

    assign_resp = await client.patch(
        f"/api/v1/inbox/conversations/{convo_id}/assign",
        json={"owner_user_id": 42},
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["owner_user_id"] == 42

    state_resp = await client.patch(
        f"/api/v1/inbox/conversations/{convo_id}/state",
        json={"status": "in_review", "priority": "high"},
    )
    assert state_resp.status_code == 200
    state_body = state_resp.json()
    assert state_body["status"] == "in_review"
    assert state_body["priority"] == "high"


async def test_conversation_state_update_preserves_sla_when_not_provided(client):
    await _seed_email_for_org1(
        gmail_id="unified-email-sla",
        from_address="sla-owner@example.com",
        is_read=False,
    )

    conversations_resp = await client.get("/api/v1/inbox/conversations?limit=20")
    assert conversations_resp.status_code == 200
    conversations = conversations_resp.json()
    convo = next(c for c in conversations if c["channel"] == "email" and c["participant"] == "sla-owner@example.com")
    convo_id = convo["conversation_id"]

    first_state = await client.patch(
        f"/api/v1/inbox/conversations/{convo_id}/state",
        json={"status": "in_review", "priority": "high", "sla_due_at": "2026-02-28T12:00:00Z"},
    )
    assert first_state.status_code == 200
    first_body = first_state.json()
    assert first_body["sla_due_at"] is not None

    second_state = await client.patch(
        f"/api/v1/inbox/conversations/{convo_id}/state",
        json={"status": "waiting"},
    )
    assert second_state.status_code == 200
    second_body = second_state.json()
    assert second_body["status"] == "waiting"
    assert second_body["sla_due_at"] == first_body["sla_due_at"]
